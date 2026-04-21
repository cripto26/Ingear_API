from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, or_, select
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

CUENTA_COBRO_STORED_FIELDS = frozenset(
    {
        "cliente_id",
        "cliente_nombre",
        "nit",
        "direccion",
        "telefono",
        "proyecto",
        "numero_contrato",
        "id_cotizacion",
    }
)

CUENTA_COBRO_LOCKED_PREFILL_FIELDS = frozenset(
    {"oportunidad_id", "cliente_id", "id_cotizacion"}
)


def _build_storage_payload(payload: dict) -> dict:
    return {
        field: value
        for field, value in payload.items()
        if field in CUENTA_COBRO_STORED_FIELDS
    }


def _hydrate_cuenta_cobro_relations(db: Session, cuentas: list) -> list:
    if not cuentas:
        return cuentas

    cotizacion_ids = {
        int(cuenta.id_cotizacion)
        for cuenta in cuentas
        if getattr(cuenta, "id_cotizacion", None) is not None
    }
    cotizaciones = {}
    if cotizacion_ids:
        cotizaciones = {
            int(cotizacion_id): (
                int(oportunidad_id) if oportunidad_id is not None else None
            )
            for cotizacion_id, oportunidad_id in db.execute(
                select(Cotizacion.id, Cotizacion.id_oportunidad).where(
                    Cotizacion.id.in_(cotizacion_ids)
                )
            ).all()
        }

    project_names = {
        cuenta.proyecto
        for cuenta in cuentas
        if getattr(cuenta, "proyecto", None)
    }
    opportunity_ids = {
        oportunidad_id
        for oportunidad_id in cotizaciones.values()
        if oportunidad_id is not None
    }

    proyectos_by_pair = {}
    proyectos_by_name = {}
    proyectos_by_opportunity = {}
    if project_names or opportunity_ids:
        stmt = select(Proyecto.id, Proyecto.nombre, Proyecto.oportunidad_id)
        filters = []
        if project_names:
            filters.append(Proyecto.nombre.in_(project_names))
        if opportunity_ids:
            filters.append(Proyecto.oportunidad_id.in_(opportunity_ids))

        for proyecto_id, nombre, oportunidad_id in db.execute(
            stmt.where(or_(*filters))
        ).all():
            info = {
                "id": int(proyecto_id),
                "oportunidad_id": (
                    int(oportunidad_id) if oportunidad_id is not None else None
                ),
            }

            if nombre:
                proyectos_by_name.setdefault(nombre, info)
            if oportunidad_id is not None:
                opportunity_key = int(oportunidad_id)
                proyectos_by_opportunity.setdefault(opportunity_key, info)
                if nombre:
                    proyectos_by_pair.setdefault((opportunity_key, nombre), info)

    for cuenta in cuentas:
        oportunidad_id = None
        if getattr(cuenta, "id_cotizacion", None) is not None:
            oportunidad_id = cotizaciones.get(int(cuenta.id_cotizacion))

        project_info = None
        project_name = getattr(cuenta, "proyecto", None)
        if oportunidad_id is not None and project_name:
            project_info = proyectos_by_pair.get((oportunidad_id, project_name))
        if project_info is None and oportunidad_id is not None:
            project_info = proyectos_by_opportunity.get(oportunidad_id)
        if project_info is None and project_name:
            project_info = proyectos_by_name.get(project_name)

        cuenta.proyecto_id = project_info["id"] if project_info else None
        cuenta.oportunidad_id = oportunidad_id
        if cuenta.oportunidad_id is None and project_info:
            cuenta.oportunidad_id = project_info["oportunidad_id"]

    return cuentas


def _set_virtual_relation_fields(
    cuenta,
    *,
    proyecto_id: int | None,
    oportunidad_id: int | None,
):
    cuenta.proyecto_id = proyecto_id
    cuenta.oportunidad_id = oportunidad_id
    return cuenta


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
        if field in CUENTA_COBRO_LOCKED_PREFILL_FIELDS:
            next_payload[field] = value
        elif current is None:
            next_payload[field] = value

    return next_payload


@router.get("/", response_model=list[CuentaCobroOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    cuentas = crud_cuenta_cobro.list(db, skip=skip, limit=limit)
    return _hydrate_cuenta_cobro_relations(db, cuentas)


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
    _hydrate_cuenta_cobro_relations(db, [obj])
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
    obj = crud_cuenta_cobro.create(db, _build_storage_payload(data))
    return _set_virtual_relation_fields(
        obj,
        proyecto_id=data.get("proyecto_id"),
        oportunidad_id=data.get("oportunidad_id"),
    )


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
    _hydrate_cuenta_cobro_relations(db, [obj])

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
    current_project_id = getattr(obj, "proyecto_id", None)
    current_opportunity_id = getattr(obj, "oportunidad_id", None)
    updated = crud_cuenta_cobro.update(db, obj, _build_storage_payload(data))
    return _set_virtual_relation_fields(
        updated,
        proyecto_id=data.get("proyecto_id", current_project_id),
        oportunidad_id=data.get("oportunidad_id", current_opportunity_id),
    )


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
