import io
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.db.session import get_db
from app.models.empleado import Empleado
from app.models.producto import Producto
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


def _normalize_product_code(value) -> str:
    return str(value or "").strip()


def _build_duplicate_code_message(code: str) -> str:
    return f"Ya existe otro producto con el codigo '{code}'. Usa un codigo diferente."


def _validate_unique_product_code(
    db: Session,
    codigo_producto,
    *,
    exclude_id: int | None = None,
) -> str:
    normalized_code = _normalize_product_code(codigo_producto)
    if not normalized_code:
        raise HTTPException(
            status_code=422,
            detail="Debes completar el codigo del producto.",
        )

    stmt = select(Producto.id).where(Producto.codigo_producto == normalized_code)
    if exclude_id is not None:
        stmt = stmt.where(Producto.id != exclude_id)

    existing_id = db.execute(stmt.limit(1)).scalar_one_or_none()
    if existing_id is not None:
        raise HTTPException(
            status_code=409,
            detail=_build_duplicate_code_message(normalized_code),
        )

    return normalized_code


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
    data["codigo_producto"] = _validate_unique_product_code(
        db,
        data.get("codigo_producto"),
    )
    try:
        return crud_producto.create(db, data)
    except HTTPException as exc:
        if exc.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail=_build_duplicate_code_message(data["codigo_producto"]),
            ) from exc
        raise


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
    if "codigo_producto" in data:
        data["codigo_producto"] = _validate_unique_product_code(
            db,
            data.get("codigo_producto"),
            exclude_id=producto_id,
        )
    try:
        return crud_producto.update(db, obj, data)
    except HTTPException as exc:
        if exc.status_code == 409:
            conflict_code = _normalize_product_code(
                data.get("codigo_producto", obj.codigo_producto)
            )
            raise HTTPException(
                status_code=409,
                detail=_build_duplicate_code_message(conflict_code),
            ) from exc
        raise


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
