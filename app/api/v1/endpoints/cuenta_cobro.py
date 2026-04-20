from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import require_any_access
from app.crud.cuenta_cobro import crud_cuenta_cobro
from app.db.session import get_db
from app.models.cliente import Cliente
from app.models.cotizacion import Cotizacion
from app.models.empleado import Empleado
from app.models.oportunidad import Oportunidad
from app.models.proyecto import Proyecto
from app.schemas.cuenta_cobro import (
    CuentaCobroCreate,
    CuentaCobroOut,
    CuentaCobroPrefill,
    CuentaCobroUpdate,
)

router = APIRouter()
project_access = require_any_access(
    roles=("GERENCIA", "LOGISTICA", "INGENIERIA"),
    permissions=("comercial.cotizador", "comercial.oportunidades"),
)


def _get_project_with_relations(
    db: Session, proyecto_id: int | None
) -> Proyecto | None:
    if not proyecto_id:
        return None

    stmt = (
        select(Proyecto)
        .options(
            joinedload(Proyecto.oportunidad).joinedload(Oportunidad.cliente),
            selectinload(Proyecto.clientes),
        )
        .where(Proyecto.id == proyecto_id)
    )
    return db.execute(stmt).unique().scalars().first()


def _resolve_prefill_payload(db: Session, proyecto: Proyecto) -> dict:
    cliente = None
    if proyecto.oportunidad and proyecto.oportunidad.cliente:
        cliente = proyecto.oportunidad.cliente
    elif proyecto.clientes:
        cliente = proyecto.clientes[0]

    cotizacion = None
    oportunidad_id = int(proyecto.oportunidad_id) if proyecto.oportunidad_id else None
    if oportunidad_id:
        cotizacion = db.execute(
            select(Cotizacion)
            .where(Cotizacion.id_oportunidad == oportunidad_id)
            .order_by(desc(Cotizacion.id))
            .limit(1)
        ).scalars().first()

    return {
        "proyecto_id": proyecto.id,
        "oportunidad_id": oportunidad_id,
        "cliente_id": getattr(cliente, "id", None),
        "cliente_nombre": getattr(cliente, "razon_social", None),
        "nit": getattr(cliente, "nit", None),
        "direccion": getattr(cliente, "direccion", None),
        "telefono": getattr(cliente, "telefono", None),
        "proyecto": proyecto.nombre,
        "numero_contrato": None,
        "id_cotizacion": getattr(cotizacion, "id", None),
    }


def _assert_related_rows(
    db: Session,
    *,
    oportunidad_id: int | None,
    cliente_id: int | None,
    cotizacion_id: int | None,
) -> None:
    if oportunidad_id and not db.get(Oportunidad, oportunidad_id):
        raise HTTPException(
            status_code=400, detail="La oportunidad asociada no existe."
        )

    if cliente_id and not db.get(Cliente, cliente_id):
        raise HTTPException(
            status_code=400, detail="El cliente asociado no existe."
        )

    if cotizacion_id and not db.get(Cotizacion, cotizacion_id):
        raise HTTPException(
            status_code=400, detail="La cotizacion asociada no existe."
        )


def _merge_prefill_defaults(
    db: Session,
    payload: dict,
    *,
    proyecto: Proyecto | None,
) -> dict:
    if not proyecto:
        return payload

    next_payload = {**payload}
    prefill = _resolve_prefill_payload(db=db, proyecto=proyecto)

    for field, value in prefill.items():
        current = next_payload.get(field)
        if current is None:
            next_payload[field] = value

    return next_payload


@router.get("/", response_model=list[CuentaCobroOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    return crud_cuenta_cobro.list(db, skip=skip, limit=limit)


@router.get("/prefill/proyecto/{proyecto_id}", response_model=CuentaCobroPrefill)
def obtener_prefill(
    proyecto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    proyecto = _get_project_with_relations(db, proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    return CuentaCobroPrefill(**_resolve_prefill_payload(db, proyecto))


@router.get("/{cuenta_cobro_id}", response_model=CuentaCobroOut)
def obtener(
    cuenta_cobro_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    obj = crud_cuenta_cobro.get(db, cuenta_cobro_id)
    if not obj:
        raise HTTPException(
            status_code=404, detail="Cuenta de cobro no encontrada"
        )
    return obj


@router.post("/", response_model=CuentaCobroOut, status_code=201)
def crear(
    payload: CuentaCobroCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    proyecto = _get_project_with_relations(db, payload.proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=400, detail="El proyecto no existe.")

    data = payload.model_dump()
    data = _merge_prefill_defaults(db, data, proyecto=proyecto)
    _assert_related_rows(
        db,
        oportunidad_id=data.get("oportunidad_id"),
        cliente_id=data.get("cliente_id"),
        cotizacion_id=data.get("id_cotizacion"),
    )
    return crud_cuenta_cobro.create(db, data)


@router.put("/{cuenta_cobro_id}", response_model=CuentaCobroOut)
def actualizar(
    cuenta_cobro_id: int,
    payload: CuentaCobroUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    obj = crud_cuenta_cobro.get(db, cuenta_cobro_id)
    if not obj:
        raise HTTPException(
            status_code=404, detail="Cuenta de cobro no encontrada"
        )

    data = payload.model_dump(exclude_unset=True)
    project_changed = (
        "proyecto_id" in data
        and data["proyecto_id"] is not None
        and data["proyecto_id"] != getattr(obj, "proyecto_id", None)
    )

    proyecto = None
    if "proyecto_id" in data:
        if not data["proyecto_id"]:
            raise HTTPException(
                status_code=400, detail="El proyecto es obligatorio."
            )
        proyecto = _get_project_with_relations(db, data["proyecto_id"])
        if not proyecto:
            raise HTTPException(status_code=400, detail="El proyecto no existe.")

    if project_changed and proyecto:
        data = _merge_prefill_defaults(db, data, proyecto=proyecto)

    _assert_related_rows(
        db,
        oportunidad_id=data.get("oportunidad_id", getattr(obj, "oportunidad_id", None)),
        cliente_id=data.get("cliente_id", getattr(obj, "cliente_id", None)),
        cotizacion_id=data.get(
            "id_cotizacion", getattr(obj, "id_cotizacion", None)
        ),
    )
    return crud_cuenta_cobro.update(db, obj, data)


@router.delete("/{cuenta_cobro_id}", status_code=204)
def eliminar(
    cuenta_cobro_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    deleted = crud_cuenta_cobro.remove(db, cuenta_cobro_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Cuenta de cobro no encontrada"
        )
    return None
