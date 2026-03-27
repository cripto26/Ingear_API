import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.producto import Producto
from app.schemas.cotizacion import CotizacionCreate, CotizacionOut, CotizacionUpdate
from app.crud.cotizacion import crud_cotizacion
from app.schemas.cotizacion_version import CotizacionVersionOut


router = APIRouter()


def _serialize_productos(productos):
    if productos is None:
        return None
    return json.dumps(productos, ensure_ascii=False)


def _validar_productos_existentes(db: Session, productos) -> None:
    if not productos:
        return

    ids_producto = sorted({item["id_producto"] for item in productos})
    stmt = select(Producto.id).where(Producto.id.in_(ids_producto))
    ids_existentes = set(db.execute(stmt).scalars().all())
    ids_faltantes = [producto_id for producto_id in ids_producto if producto_id not in ids_existentes]

    if ids_faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Productos no encontrados: {ids_faltantes}",
        )


@router.get("/", response_model=list[CotizacionOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_cotizacion.list(db, skip=skip, limit=limit)


@router.get("/{cotizacion_id}", response_model=CotizacionOut)
def obtener(cotizacion_id: int, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return obj


@router.post("/", response_model=CotizacionOut, status_code=201)
def crear(payload: CotizacionCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    _validar_productos_existentes(db, data["productos"])
    data["productos"] = _serialize_productos(data["productos"])
    return crud_cotizacion.create(db, data)


@router.put("/{cotizacion_id}", response_model=CotizacionOut)
def actualizar(cotizacion_id: int, payload: CotizacionUpdate, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    data = payload.model_dump(exclude_unset=True)
    if "productos" in data:
        _validar_productos_existentes(db, data["productos"])
        data["productos"] = _serialize_productos(data["productos"])

    return crud_cotizacion.update(db, obj, data)


@router.delete("/{cotizacion_id}", status_code=204)
def eliminar(cotizacion_id: int, db: Session = Depends(get_db)):
    deleted = crud_cotizacion.remove(db, cotizacion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return None

@router.get("/{cotizacion_id}/versiones", response_model=list[CotizacionVersionOut])
def listar_versiones(cotizacion_id: int, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return crud_cotizacion.list_versions(db, cotizacion_id)


@router.get("/{cotizacion_id}/versiones/{numero_version}", response_model=CotizacionVersionOut)
def obtener_version(cotizacion_id: int, numero_version: int, db: Session = Depends(get_db)):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    version = crud_cotizacion.get_version(db, cotizacion_id, numero_version)
    if not version:
        raise HTTPException(status_code=404, detail="Version de cotizacion no encontrada")

    return version
