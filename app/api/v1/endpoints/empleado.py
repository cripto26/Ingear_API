from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.empleado import EmpleadoCreate, EmpleadoUpdate, EmpleadoOut
from app.crud.empleado import crud_empleado

router = APIRouter()


@router.get("/", response_model=list[EmpleadoOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_empleado.list(db, skip=skip, limit=limit)


@router.get("/{empleado_id}", response_model=EmpleadoOut)
def obtener(empleado_id: int, db: Session = Depends(get_db)):
    obj = crud_empleado.get(db, empleado_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return obj


@router.post("/", response_model=EmpleadoOut, status_code=201)
def crear(payload: EmpleadoCreate, db: Session = Depends(get_db)):
    return crud_empleado.create(db, payload.model_dump())


@router.put("/{empleado_id}", response_model=EmpleadoOut)
def actualizar(empleado_id: int, payload: EmpleadoUpdate, db: Session = Depends(get_db)):
    obj = crud_empleado.get(db, empleado_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return crud_empleado.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{empleado_id}", status_code=204)
def eliminar(empleado_id: int, db: Session = Depends(get_db)):
    deleted = crud_empleado.remove(db, empleado_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return None
