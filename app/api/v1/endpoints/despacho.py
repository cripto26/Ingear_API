from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_any_access
from app.db.session import get_db
from app.models.empleado import Empleado
from app.schemas.despacho import DespachoCreate, DespachoUpdate, DespachoOut
from app.crud.despacho import crud_despacho

router = APIRouter()
despacho_access = require_any_access(roles=("GERENCIA", "LOGISTICA"))


@router.get("/", response_model=list[DespachoOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(despacho_access),
):
    return crud_despacho.list(db, skip=skip, limit=limit)


@router.get("/{despacho_id}", response_model=DespachoOut)
def obtener(
    despacho_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(despacho_access),
):
    obj = crud_despacho.get(db, despacho_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return obj


@router.post("/", response_model=DespachoOut, status_code=201)
def crear(
    payload: DespachoCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(despacho_access),
):
    return crud_despacho.create(db, payload.model_dump())


@router.put("/{despacho_id}", response_model=DespachoOut)
def actualizar(
    despacho_id: int,
    payload: DespachoUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(despacho_access),
):
    obj = crud_despacho.get(db, despacho_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return crud_despacho.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{despacho_id}", status_code=204)
def eliminar(
    despacho_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(despacho_access),
):
    deleted = crud_despacho.remove(db, despacho_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return None
