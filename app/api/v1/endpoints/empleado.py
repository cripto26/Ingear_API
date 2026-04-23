from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_view_permissions
from app.db.session import get_db
from app.models.empleado import Empleado
from app.schemas.empleado import EmpleadoCreate, EmpleadoUpdate, EmpleadoOut
from app.crud.empleado import crud_empleado

router = APIRouter()



def validate_jefe_id(
    db: Session,
    jefe_id: int | None,
    *,
    empleado_id: int | None = None,
) -> None:
    if jefe_id is None:
        return

    if empleado_id is not None and jefe_id == empleado_id:
        raise HTTPException(
            status_code=400,
            detail="Un empleado no puede asignarse como su propio jefe directo.",
        )

    jefe = crud_empleado.get(db, jefe_id)
    if not jefe:
        raise HTTPException(status_code=400, detail="El jefe directo no existe.")


@router.get("/", response_model=list[EmpleadoOut])
def listar(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(require_roles("GERENCIA")),
):
    return crud_empleado.list(db, skip=skip, limit=limit)

@router.get("/{empleado_id}", response_model=EmpleadoOut)
def obtener(
    empleado_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(require_roles("GERENCIA")),
):
    obj = crud_empleado.get(db, empleado_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return obj


@router.post("/", response_model=EmpleadoOut, status_code=201)
def crear(
    payload: EmpleadoCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(require_roles("GERENCIA")),
):
    validate_jefe_id(db, payload.jefe_id)

    try:
        return crud_empleado.create_secure(db, payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="La cedula ya esta registrada")


@router.put("/{empleado_id}", response_model=EmpleadoOut)
def actualizar(
    empleado_id: int,
    payload: EmpleadoUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(require_roles("GERENCIA")),
):
    obj = crud_empleado.get(db, empleado_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    if "jefe_id" in payload.model_fields_set:
        validate_jefe_id(db, payload.jefe_id, empleado_id=empleado_id)

    try:
        return crud_empleado.update_secure(
            db,
            obj,
            payload.model_dump(exclude_unset=True),
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="La cedula ya esta registrada")


@router.delete("/{empleado_id}", status_code=204)
def eliminar(
    empleado_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(require_roles("GERENCIA")),
):
    deleted = crud_empleado.remove(db, empleado_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return None
