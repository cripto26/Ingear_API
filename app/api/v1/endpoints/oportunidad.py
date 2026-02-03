from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.oportunidad import OportunidadCreate, OportunidadUpdate, OportunidadOut
from app.crud.oportunidad import crud_oportunidad

router = APIRouter()


@router.get("/", response_model=list[OportunidadOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_oportunidad.list(db, skip=skip, limit=limit)


@router.get("/{oportunidad_id}", response_model=OportunidadOut)
def obtener(oportunidad_id: int, db: Session = Depends(get_db)):
    obj = crud_oportunidad.get(db, oportunidad_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return obj


@router.post("/", response_model=OportunidadOut, status_code=201)
def crear(payload: OportunidadCreate, db: Session = Depends(get_db)):
    return crud_oportunidad.create(db, payload.model_dump())


@router.put("/{oportunidad_id}", response_model=OportunidadOut)
def actualizar(oportunidad_id: int, payload: OportunidadUpdate, db: Session = Depends(get_db)):
    obj = crud_oportunidad.get(db, oportunidad_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return crud_oportunidad.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{oportunidad_id}", status_code=204)
def eliminar(oportunidad_id: int, db: Session = Depends(get_db)):
    deleted = crud_oportunidad.remove(db, oportunidad_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return None
