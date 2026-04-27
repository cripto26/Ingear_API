import io
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.db.session import get_db
from app.models.empleado import Empleado
from app.schemas.producto import ProductoCreate, ProductoUpdate, ProductoOut
from app.crud.producto import crud_producto
from app.services.product_image_service import build_product_thumbnail_from_drive_url

router = APIRouter()
product_access = require_view_permissions("comercial.productos")


def _normalize_lookup(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFD", str(value or "").strip().lower())
        if unicodedata.category(char) != "Mn"
    )


def _calculate_costo_ingear(precio_pvp, descuento_fabricante):
    if precio_pvp is None:
        return None

    pvp = max(Decimal("0"), Decimal(str(precio_pvp)))
    discount_pct = Decimal(str(descuento_fabricante or 0))
    discount_pct = min(max(Decimal("0"), discount_pct), Decimal("100"))
    cost = pvp * (Decimal("1") - (discount_pct / Decimal("100")))
    return cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _payload_with_calculated_costo_ingear(data: dict, current=None) -> dict:
    pais_origen = data.get("pais_origen", getattr(current, "pais_origen", None))
    normalized_country = _normalize_lookup(pais_origen)

    if not normalized_country or normalized_country == "colombia":
        return data

    precio_pvp = data.get("precio_pvp", getattr(current, "precio_pvp", None))
    descuento_fabricante = data.get(
        "descuento_fabricante",
        getattr(current, "descuento_fabricante", None),
    )
    costo_ingear = _calculate_costo_ingear(precio_pvp, descuento_fabricante)

    if costo_ingear is not None:
        data["costo_ingear"] = costo_ingear

    return data


@router.get("/", response_model=list[ProductoOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
    return crud_producto.list(db, skip=skip, limit=limit)


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(
    producto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return obj


@router.get("/{producto_id}/imagen")
def obtener_imagen_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
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
def crear(
    payload: ProductoCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
    data = _payload_with_calculated_costo_ingear(payload.model_dump())
    return crud_producto.create(db, data)


@router.put("/{producto_id}", response_model=ProductoOut)
def actualizar(
    producto_id: int,
    payload: ProductoUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    data = _payload_with_calculated_costo_ingear(
        payload.model_dump(exclude_unset=True),
        current=obj,
    )
    return crud_producto.update(db, obj, data)


@router.delete("/{producto_id}", status_code=204)
def eliminar(
    producto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_access),
):
    deleted = crud_producto.remove(db, producto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return None
