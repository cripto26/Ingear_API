from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_any_access
from app.models.oportunidad import Oportunidad
from app.db.session import get_db
from app.models.empleado import Empleado
from app.models.proyecto import Proyecto
from app.schemas.proyecto import ProyectoCreate, ProyectoUpdate, ProyectoOut
from app.crud.proyecto import crud_proyecto

router = APIRouter()
project_access = require_any_access(
    roles=("GERENCIA", "LOGISTICA", "INGENIERIA"),
    permissions=("comercial.proyectos",),
)

def _validate_unique_project_link(
    db: Session,
    oportunidad_id: int | None,
    *,
    exclude_project_id: int | None = None,
) -> None:
    if not oportunidad_id:
        return

    oportunidad = db.get(Oportunidad, oportunidad_id)
    if not oportunidad:
        raise HTTPException(
            status_code=400,
            detail="La oportunidad asociada no existe.",
        )

    stmt = select(Proyecto).where(Proyecto.oportunidad_id == oportunidad_id)
    if exclude_project_id is not None:
        stmt = stmt.where(Proyecto.id != exclude_project_id)

    proyecto_existente = db.execute(stmt.limit(1)).scalars().first()
    if proyecto_existente:
        raise HTTPException(
            status_code=409,
            detail="La oportunidad ya tiene un proyecto ligado.",
        )


@router.get("/", response_model=list[ProyectoOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    return crud_proyecto.list(db, skip=skip, limit=limit)


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def obtener(
    proyecto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    obj = crud_proyecto.get(db, proyecto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return obj


@router.post("/", response_model=ProyectoOut, status_code=201)
def crear(
    payload: ProyectoCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    _validate_unique_project_link(db, payload.oportunidad_id)
    return crud_proyecto.create(db, payload.model_dump())


@router.put("/{proyecto_id}", response_model=ProyectoOut)
def actualizar(
    proyecto_id: int,
    payload: ProyectoUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    obj = crud_proyecto.get(db, proyecto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    data = payload.model_dump(exclude_unset=True)
    target_oportunidad_id = data.get("oportunidad_id")
    if (
        target_oportunidad_id
        and target_oportunidad_id != getattr(obj, "oportunidad_id", None)
    ):
        _validate_unique_project_link(
            db,
            target_oportunidad_id,
            exclude_project_id=proyecto_id,
        )

    return crud_proyecto.update(db, obj, data)


@router.delete("/{proyecto_id}", status_code=204)
def eliminar(
    proyecto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(project_access),
):
    deleted = crud_proyecto.remove(db, proyecto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return None
