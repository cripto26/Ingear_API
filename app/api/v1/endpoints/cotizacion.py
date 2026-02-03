from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cotizacion import CotizacionCreate, CotizacionUpdate, CotizacionOut
from app.crud.cotizacion import crud_cotizacion

router = APIRouter()


@router.get("/", response_model=list[CotizacionOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_cotizacion.list(db, skip=skip, limit=limit)


@router.get("/{cotizacion_id}", response_model=CotizacionOut)
def obtener(cotizacion_id: int, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return obj


@router.post("/", response_model=CotizacionOut, status_code=201)
def crear(payload: CotizacionCreate, db: Session = Depends(get_db)):
    return crud_cotizacion.create(db, payload.model_dump())


@router.put("/{cotizacion_id}", response_model=CotizacionOut)
def actualizar(cotizacion_id: int, payload: CotizacionUpdate, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return crud_cotizacion.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{cotizacion_id}", status_code=204)
def eliminar(cotizacion_id: int, db: Session = Depends(get_db)):
    deleted = crud_cotizacion.remove(db, cotizacion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return None
