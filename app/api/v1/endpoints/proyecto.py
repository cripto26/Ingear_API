from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.proyecto import ProyectoCreate, ProyectoUpdate, ProyectoOut
from app.crud.proyecto import crud_proyecto

router = APIRouter()


@router.get("/", response_model=list[ProyectoOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_proyecto.list(db, skip=skip, limit=limit)


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def obtener(proyecto_id: int, db: Session = Depends(get_db)):
    obj = crud_proyecto.get(db, proyecto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return obj


@router.post("/", response_model=ProyectoOut, status_code=201)
def crear(payload: ProyectoCreate, db: Session = Depends(get_db)):
    return crud_proyecto.create(db, payload.model_dump())


@router.put("/{proyecto_id}", response_model=ProyectoOut)
def actualizar(proyecto_id: int, payload: ProyectoUpdate, db: Session = Depends(get_db)):
    obj = crud_proyecto.get(db, proyecto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return crud_proyecto.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{proyecto_id}", status_code=204)
def eliminar(proyecto_id: int, db: Session = Depends(get_db)):
    deleted = crud_proyecto.remove(db, proyecto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return None
