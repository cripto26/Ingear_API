import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.producto import ProductoCreate, ProductoUpdate, ProductoOut
from app.crud.producto import crud_producto
from app.services.product_image_service import build_product_thumbnail_from_drive_url

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


@router.get("/{producto_id}/imagen")
def obtener_imagen_producto(producto_id: int, db: Session = Depends(get_db)):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if not obj.url_imagen:
        raise HTTPException(status_code=404, detail="Producto sin imagen")

    try:
        image_bytes = build_product_thumbnail_from_drive_url(
            obj.url_imagen,
            width=140,
            height=90,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Aquí caerán errores de permisos, archivo inexistente o credenciales
        raise HTTPException(status_code=502, detail=f"No se pudo obtener la imagen: {e}")

    headers = {
        "Cache-Control": "public, max-age=3600"
    }

    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/jpeg",
        headers=headers,
    )


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