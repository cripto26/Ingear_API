import io
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.core.security import infer_role
from app.core.view_permissions import (
    has_view_permission_version_marker,
    normalize_commercial_view_permissions,
)
from app.db.session import get_db
from app.models.empleado import Empleado
from app.models.notificacion import Notificacion
from app.models.producto import Producto
from app.schemas.producto import (
    ProductoCreate,
    ProductoUpdate,
    ProductoOut,
    WorldOfficeInventoryStatusOut,
    WorldOfficeInventorySyncOut,
    WorldOfficeProductImportOut,
)
from app.crud.producto import crud_producto
from app.services.product_image_service import (
    build_product_thumbnail_from_drive_url,
    build_product_thumbnail_from_uploaded_image_url,
    is_uploaded_product_image_url,
    save_uploaded_product_image,
)
from app.services.notificacion_service import (
    create_notification,
    resolve_notifications_for_entity,
)
from app.services.world_office_inventory_service import (
    WorldOfficeInventoryError,
    apply_world_office_inventory,
    get_world_office_inventory_status,
    import_missing_world_office_products,
    sync_world_office_inventory_to_products,
)

router = APIRouter()
product_access = require_view_permissions("comercial.productos")
product_data_request_access = require_view_permissions("comercial.cotizador")

PRODUCT_VALUES_PERMISSION = "comercial.productos.valores-edicion"
product_image_upload_access = require_view_permissions(
    "comercial.cotizador",
    PRODUCT_VALUES_PERMISSION,
)
PRODUCT_SENSITIVE_VALUE_FIELDS = (
    "costo_fabrica",
    "descuento_fabricante",
    "costo_ingear",
    "valor_inventario",
    "precio_pvp",
    "precio_inventario",
)

PRODUCT_DATA_RESPONSIBLE_CARGOS = {
    "analista de costos y presupuestos",
    "gerente comercial",
    "gerente",
}

PRODUCT_DATA_MISSING_FIELD_LABELS = {
    "pais_origen": "pais de origen",
    "ciudad": "ciudad de origen",
    "costo_origen": "costo de origen",
    "peso_kg": "peso",
    "volumen": "volumen",
    "precio_pvp": "precio PVP",
    "precio_inventario": "precio inventario",
    "cantidad_inventario": "cantidad inventario",
}


def product_values_access(current: Empleado = Depends(product_access)):
    if _can_view_product_values(current):
        return current

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No autorizado",
    )


def _can_view_product_values(current: Empleado) -> bool:
    permissions = getattr(current, "permisos_vistas", None)
    normalized = normalize_commercial_view_permissions(permissions) or []

    if has_view_permission_version_marker(permissions):
        return PRODUCT_VALUES_PERMISSION in normalized

    return (
        PRODUCT_VALUES_PERMISSION in normalized
        or (
            permissions is None
            and infer_role(
                getattr(current, "area", None),
                getattr(current, "cargo", None),
            )
            == "GERENCIA"
        )
    )


def _serialize_product_for_permissions(producto: Producto, current: Empleado) -> dict:
    data = ProductoOut.model_validate(producto).model_dump()
    if _can_view_product_values(current):
        return data

    for field in PRODUCT_SENSITIVE_VALUE_FIELDS:
        data[field] = None

    return data


class ProductoDataRequestIn(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    product_label: str | None = None
    quote_title: str | None = None
    item_number: int | None = None


class ProductoDataRequestOut(BaseModel):
    created: int
    reused: int
    recipients: list[str]
    detail: str


def _normalize_lookup(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFD", str(value or "").strip().lower())
        if unicodedata.category(char) != "Mn"
    )


def _is_active_employee(empleado: Empleado) -> bool:
    estado = _normalize_lookup(getattr(empleado, "estado", None))
    return estado not in {"inactivo", "retirado", "bloqueado"}


def _is_product_data_responsible(empleado: Empleado) -> bool:
    return _normalize_lookup(empleado.cargo) in PRODUCT_DATA_RESPONSIBLE_CARGOS


def _format_missing_fields(fields: list[str]) -> str:
    labels: list[str] = []
    seen: set[str] = set()

    for field in fields:
        key = str(field or "").strip()
        if not key:
            continue

        label = PRODUCT_DATA_MISSING_FIELD_LABELS.get(key, key)
        if label in seen:
            continue

        seen.add(label)
        labels.append(label)

    if not labels:
        return "datos requeridos para cotizar"

    if len(labels) == 1:
        return labels[0]

    if len(labels) == 2:
        return f"{labels[0]} y {labels[1]}"

    return f"{', '.join(labels[:-1])} y {labels[-1]}"


def _has_text_value(value) -> bool:
    return bool(str(value or "").strip())


def _has_positive_number(value) -> bool:
    try:
        return Decimal(str(value or "0")) > 0
    except Exception:
        return False


def _is_colombia_country(value) -> bool:
    return _normalize_lookup(value) == "colombia"


def _product_missing_quote_fields(producto: Producto) -> list[str]:
    missing: list[str] = []

    if not _has_text_value(producto.pais_origen):
        missing.append("pais_origen")

    if not _has_text_value(producto.ciudad):
        missing.append("ciudad")

    origin_cost = (
        producto.costo_ingear
        if _is_colombia_country(producto.pais_origen)
        else producto.costo_fabrica
    )
    if not _has_positive_number(origin_cost):
        missing.append("costo_origen")

    if not _has_positive_number(producto.peso_kg):
        missing.append("peso_kg")

    if not _has_positive_number(producto.volumen):
        missing.append("volumen")

    return missing


def _build_product_notification_label(
    producto: Producto,
    payload: ProductoDataRequestIn,
) -> str:
    clean_payload_label = str(payload.product_label or "").strip()
    if clean_payload_label:
        return clean_payload_label

    parts = [
        str(producto.codigo_producto or producto.referencia or "").strip(),
        str(producto.descripcion or "").strip(),
    ]
    clean_parts = [part for part in parts if part]
    return " - ".join(clean_parts) or f"producto #{producto.id}"


def _list_product_data_responsibles(
    db: Session,
    current: Empleado,
) -> list[Empleado]:
    empleados = list(db.execute(select(Empleado)).scalars().all())

    return [
        empleado
        for empleado in empleados
        if empleado.id != current.id
        and _is_active_employee(empleado)
        and _is_product_data_responsible(empleado)
    ]


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
    current: Empleado = Depends(product_access),
):
    rows = crud_producto.list(db, skip=skip, limit=limit)
    apply_world_office_inventory(rows)
    return [_serialize_product_for_permissions(row, current) for row in rows]


@router.get(
    "/world-office/estado",
    response_model=WorldOfficeInventoryStatusOut,
)
def estado_world_office(
    _current: Empleado = Depends(product_access),
):
    return get_world_office_inventory_status()


@router.post(
    "/world-office/sync",
    response_model=WorldOfficeInventorySyncOut,
)
def sincronizar_inventario_world_office(
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_values_access),
):
    productos = list(db.execute(select(Producto)).scalars().all())
    try:
        stats = sync_world_office_inventory_to_products(productos)
    except WorldOfficeInventoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.commit()
    return stats


@router.post(
    "/world-office/importar-faltantes",
    response_model=WorldOfficeProductImportOut,
)
def importar_productos_faltantes_world_office(
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_values_access),
):
    try:
        stats = import_missing_world_office_products(db)
    except WorldOfficeInventoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.commit()
    return stats


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(
    producto_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(product_access),
):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    apply_world_office_inventory([obj])
    return _serialize_product_for_permissions(obj, current)


@router.get("/{producto_id}/datos-cotizador", response_model=ProductoOut)
def obtener_datos_cotizador(
    producto_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_data_request_access),
):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    apply_world_office_inventory([obj])
    if not _product_missing_quote_fields(obj):
        resolved = resolve_notifications_for_entity(
            db,
            entidad_tipo="producto",
            entidad_id=producto_id,
            tipo="producto.datos_faltantes",
        )
        if resolved:
            db.commit()
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
        if is_uploaded_product_image_url(obj.url_imagen):
            image_bytes = build_product_thumbnail_from_uploaded_image_url(
                obj.url_imagen,
                width=140,
                height=90,
            )
        else:
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


@router.post("/{producto_id}/imagen", response_model=ProductoOut)
async def subir_imagen_producto(
    producto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Empleado = Depends(product_image_upload_access),
):
    obj = crud_producto.get(db, producto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    raw_bytes = await request.body()
    try:
        image_url = save_uploaded_product_image(producto_id, raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = crud_producto.update(db, obj, {"url_imagen": image_url})
    return _serialize_product_for_permissions(updated, current)


@router.post(
    "/{producto_id}/solicitar-datos-cotizador",
    response_model=ProductoDataRequestOut,
)
def solicitar_datos_producto_desde_cotizador(
    producto_id: int,
    payload: ProductoDataRequestIn,
    db: Session = Depends(get_db),
    current: Empleado = Depends(product_data_request_access),
):
    producto = crud_producto.get(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    responsables = _list_product_data_responsibles(db, current)
    if not responsables:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontraron responsables activos para completar datos "
                "de producto."
            ),
        )

    product_label = _build_product_notification_label(producto, payload)
    missing_label = _format_missing_fields(payload.missing_fields)
    quote_title = str(payload.quote_title or "").strip()
    item_number = payload.item_number if payload.item_number and payload.item_number > 0 else None
    item_label = f"Item {item_number}. " if item_number else ""
    quote_label = f" Cotizacion: {quote_title}." if quote_title else ""
    message = (
        f"{current.nombre} solicita completar datos del producto "
        f"{product_label}. {item_label}Faltan: {missing_label}.{quote_label}"
    )
    route = f"/cotizador?productId={producto.id}&quoteProductRequest=1"

    created = 0
    reused = 0
    recipient_names: list[str] = []

    for responsable in responsables:
        recipient_names.append(responsable.nombre)

        existing = db.execute(
            select(Notificacion)
            .where(
                Notificacion.destinatario_empleado_id == responsable.id,
                Notificacion.actor_empleado_id == current.id,
                Notificacion.tipo == "producto.datos_faltantes",
                Notificacion.entidad_tipo == "producto",
                Notificacion.entidad_id == producto.id,
                Notificacion.resuelta_en.is_(None),
            )
            .limit(1)
        ).scalar_one_or_none()

        if existing:
            reused += 1
            continue

        create_notification(
            db,
            destinatario_empleado_id=responsable.id,
            actor_empleado_id=current.id,
            tipo="producto.datos_faltantes",
            area=current.area,
            titulo="Producto con datos faltantes",
            mensaje=message,
            entidad_tipo="producto",
            entidad_id=producto.id,
            ruta_destino=route,
            requiere_accion=True,
        )
        created += 1

    db.commit()

    return ProductoDataRequestOut(
        created=created,
        reused=reused,
        recipients=recipient_names,
        detail=(
            "Solicitud enviada a los responsables de producto."
            if created > 0
            else "Ya existia una solicitud pendiente para este producto."
        ),
    )


@router.post("/", response_model=ProductoOut, status_code=201)
def crear(
    payload: ProductoCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(product_values_access),
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
    _current: Empleado = Depends(product_values_access),
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
        updated = crud_producto.update(db, obj, data)
        if not _product_missing_quote_fields(updated):
            resolve_notifications_for_entity(
                db,
                entidad_tipo="producto",
                entidad_id=producto_id,
                tipo="producto.datos_faltantes",
            )
            db.commit()
        return updated
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
    _current: Empleado = Depends(product_values_access),
):
    deleted = crud_producto.remove(db, producto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return None
