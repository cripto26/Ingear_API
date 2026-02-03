from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.producto import ProductoCreate, ProductoUpdate, ProductoOut
from app.crud.producto import crud_producto

router = APIRouter()


@router.get("/", response_model=list[ProductoOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_producto.list(db, skip=skip, limit=limit)


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(producto_id: int, db: Session = Depends(get_db)):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return obj


@router.post("/", response_model=ProductoOut, status_code=201)
def crear(payload: ProductoCreate, db: Session = Depends(get_db)):
    return crud_producto.create(db, payload.model_dump())


@router.put("/{producto_id}", response_model=ProductoOut)
def actualizar(producto_id: int, payload: ProductoUpdate, db: Session = Depends(get_db)):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return crud_producto.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{producto_id}", status_code=204)
def eliminar(producto_id: int, db: Session = Depends(get_db)):
    deleted = crud_producto.remove(db, producto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return None
