from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.despacho import DespachoCreate, DespachoUpdate, DespachoOut
from app.crud.despacho import crud_despacho

router = APIRouter()


@router.get("/", response_model=list[DespachoOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_despacho.list(db, skip=skip, limit=limit)


@router.get("/{despacho_id}", response_model=DespachoOut)
def obtener(despacho_id: int, db: Session = Depends(get_db)):
    obj = crud_despacho.get(db, despacho_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return obj


@router.post("/", response_model=DespachoOut, status_code=201)
def crear(payload: DespachoCreate, db: Session = Depends(get_db)):
    return crud_despacho.create(db, payload.model_dump())


@router.put("/{despacho_id}", response_model=DespachoOut)
def actualizar(despacho_id: int, payload: DespachoUpdate, db: Session = Depends(get_db)):
    obj = crud_despacho.get(db, despacho_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return crud_despacho.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{despacho_id}", status_code=204)
def eliminar(despacho_id: int, db: Session = Depends(get_db)):
    deleted = crud_despacho.remove(db, despacho_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Despacho no encontrado")
    return None
