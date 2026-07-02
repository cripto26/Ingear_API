import json
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_empleado,
    require_any_access,
    require_view_permissions,
)
from app.core.security import infer_role
from app.core.view_permissions import has_view_permission
from app.db.session import get_db
from app.models.cotizacion import Cotizacion
from app.models.cotizacion_logistica import (
    CotizacionAprobada,
    CotizacionLogisticaRemision,
    CotizacionLogisticaRemisionItem,
    CotizacionLogisticaSeparacion,
)
from app.models.empleado import Empleado
from app.models.notificacion import Notificacion
from app.models.oportunidad import Oportunidad
from app.models.producto import Producto
from app.models.proyecto import Proyecto
from app.schemas.cotizacion import (
    CotizacionCreate,
    CotizacionEmailIn,
    CotizacionEmailOut,
    CotizacionLogisticaRemisionCreate,
    CotizacionLogisticaResumenOut,
    CotizacionLogisticaSeparacionIn,
    CotizacionLogisticaUpdate,
    CotizacionOut,
    CotizacionUpdate,
)
from app.crud.cotizacion import crud_cotizacion
from app.schemas.cotizacion_version import CotizacionVersionOut
from app.services.gmail_service import decode_pdf_base64, send_email_with_pdf
from app.services.notificacion_service import (
    create_notification,
    resolve_notifications_for_entity,
)
from app.services.oportunidad_totals import sync_oportunidad_rubro_sin_iva
from app.services.world_office_inventory_service import apply_world_office_inventory


router = APIRouter()
cotizacion_access = require_view_permissions("comercial.cotizador")
cotizacion_aprobada_access = require_any_access(
    roles=("GERENCIA", "LOGISTICA"),
    permissions=("logistica.cotizaciones",),
)
LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE = "logistica.stock.verificacion"
LOGISTICS_STOCK_RESPONSE_NOTIFICATION_TYPE = "logistica.stock.respuesta"
LOGISTICS_STOCK_REQUEST_PERMISSION = "logistica.stock.solicitar"
LOGISTICS_STOCK_UPDATE_PERMISSION = "logistica.stock.actualizar"
LOGISTICS_STOCK_STATUS_LABELS = {
    "incompleto": "Stock incompleto",
    "parcial": "Stock parcial",
    "completo": "Stock completo",
}


def _normalize_team_lookup(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", (value or "").strip().lower())
    return "".join(char for char in raw if unicodedata.category(char) != "Mn")


def _is_management_employee(empleado: Empleado | None) -> bool:
    if empleado is None:
        return False
    return infer_role(empleado.area, empleado.cargo) == "GERENCIA"


def _looks_like_commercial_team_leader(empleado: Empleado | None) -> bool:
    if empleado is None:
        return False

    cargo = _normalize_team_lookup(empleado.cargo)
    if not cargo:
        return False

    return "lider" in cargo and "proyect" in cargo


def _build_team_anchor_by_empleado_id(empleados: list[Empleado]) -> dict[int, int]:
    direct_manager_ids = {
        int(empleado.jefe_id)
        for empleado in empleados
        if empleado.jefe_id is not None
    }
    team_anchor_by_id: dict[int, int] = {}

    for empleado in empleados:
        if _is_management_employee(empleado):
            team_anchor_by_id[empleado.id] = empleado.id
            continue

        

        if (
            _looks_like_commercial_team_leader(empleado)
            or empleado.id in direct_manager_ids
        ):
            team_anchor_by_id[empleado.id] = empleado.id
            continue

        if empleado.jefe_id is not None:
            team_anchor_by_id[empleado.id] = int(empleado.jefe_id)
            continue

        team_anchor_by_id[empleado.id] = empleado.id

    return team_anchor_by_id


def _load_empleado_directory(
    db: Session,
) -> tuple[dict[int, Empleado], dict[int, int]]:
    empleados = list(db.execute(select(Empleado)).scalars().all())
    empleados_by_id = {empleado.id: empleado for empleado in empleados}
    team_anchor_by_id = _build_team_anchor_by_empleado_id(empleados)
    return empleados_by_id, team_anchor_by_id


def _set_cotizacion_responsable_name(
    cotizacion: Cotizacion,
    owner: Empleado | None,
) -> None:
    setattr(cotizacion, "empleado_nombre", owner.nombre if owner else None)


def _annotate_cotizacion_responsables(
    rows: list[Cotizacion],
    current: Empleado,
    empleados_by_id: dict[int, Empleado] | None = None,
) -> None:
    for row in rows:
        owner = (empleados_by_id or {}).get(row.id_empleado)
        if owner is None and current.id == row.id_empleado:
            owner = current
        _set_cotizacion_responsable_name(row, owner)


def _can_edit_cotizacion(
    current: Empleado,
    owner: Empleado | None,
    team_anchor_by_id: dict[int, int],
) -> bool:
    if _is_management_employee(current):
        return True

    if owner is None:
        return False

    if current.id == owner.id:
        return True

    current_anchor = team_anchor_by_id.get(current.id, current.id)
    owner_anchor = team_anchor_by_id.get(owner.id, owner.id)
    return current_anchor == owner_anchor


def _annotate_cotizacion_permissions(
    db: Session,
    current: Empleado,
    cotizaciones: Cotizacion | list[Cotizacion],
):
    rows = cotizaciones if isinstance(cotizaciones, list) else [cotizaciones]

    if _is_management_employee(current):
        empleados_by_id, _team_anchor_by_id = _load_empleado_directory(db)
        _annotate_cotizacion_responsables(rows, current, empleados_by_id)
        for row in rows:
            setattr(row, "can_edit", True)
            setattr(row, "can_duplicate", True)
        return cotizaciones

    if all(current.id == row.id_empleado for row in rows):
        _annotate_cotizacion_responsables(rows, current)
        for row in rows:
            setattr(row, "can_edit", True)
            setattr(row, "can_duplicate", True)
        return cotizaciones

    empleados_by_id, team_anchor_by_id = _load_empleado_directory(db)
    empleados_by_id.setdefault(current.id, current)
    _annotate_cotizacion_responsables(rows, current, empleados_by_id)

    for row in rows:
        owner = empleados_by_id.get(row.id_empleado)
        setattr(
            row,
            "can_edit",
            _can_edit_cotizacion(current, owner, team_anchor_by_id),
        )
        setattr(row, "can_duplicate", True)

    return cotizaciones


def _assert_can_edit_cotizacion(
    db: Session,
    current: Empleado,
    cotizacion: Cotizacion,
) -> None:
    if _is_management_employee(current) or current.id == cotizacion.id_empleado:
        return

    empleados_by_id, team_anchor_by_id = _load_empleado_directory(db)
    empleados_by_id.setdefault(current.id, current)
    owner = empleados_by_id.get(cotizacion.id_empleado)

    if _can_edit_cotizacion(current, owner, team_anchor_by_id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "No tienes permisos para editar esta cotizacion. Solo puedes "
            "editar cotizaciones de tu equipo comercial. Si pertenece a otro "
            "equipo, debes duplicarla."
        ),
    )


def _normalize_stage(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", (value or "").strip().lower())
    return "".join(char for char in raw if unicodedata.category(char) != "Mn")


def _is_won_stage(value: str | None) -> bool:
    return _normalize_stage(value) == "ganada"


def _is_approved_status(value: str | None) -> bool:
    normalized = _normalize_stage(value)
    return normalized in {"2", "aprobada"}


def _sync_cotizacion_aprobada_from_cotizacion(
    db: Session,
    cotizacion: Cotizacion,
) -> CotizacionAprobada | None:
    if not _is_approved_status(cotizacion.estado):
        return None

    approved = db.get(CotizacionAprobada, cotizacion.id)
    if approved is None:
        approved = CotizacionAprobada(
            id=cotizacion.id,
            logistica_stock=0,
            logistica_stock_estado="incompleto",
        )
        db.add(approved)

    for field_name in (
        "id_empleado",
        "id_oportunidad",
        "url_cotizacion",
        "tiempo_entrega",
        "nombre_cotizacion",
        "tipo_cotizacion",
        "etapa_cotizacion",
        "forma_pago",
        "contacto",
        "tipo_servicio",
        "trm",
        "sub_total",
        "total",
        "productos",
        "estado",
    ):
        setattr(approved, field_name, getattr(cotizacion, field_name))

    approved.fecha_creacion = (
        cotizacion.fecha_creacion or datetime.now(timezone.utc)
    )
    if not approved.logistica_stock_estado:
        approved.logistica_stock_estado = "incompleto"

    return approved


def _normalize_extension(value: str | None, fallback: str = "pdf") -> str:
    cleaned = "".join(
        char for char in str(value or fallback).lower() if char.isalnum()
    )
    return cleaned or fallback


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


def _productos_tienen_costo_fabrica_override(productos) -> bool:
    if not productos:
        return False

    return any(
        item.get("costo_fabrica_override") is not None for item in productos
    )


def _build_productos_override_fingerprint(productos) -> list[tuple[int, int, float]]:
    if not productos:
        return []

    fingerprint: list[tuple[int, int, float]] = []
    for item in productos:
        override = item.get("costo_fabrica_override")
        if override is None:
            continue

        fingerprint.append(
            (
                int(item.get("id_producto") or 0),
                int(item.get("particion") or 0),
                float(override),
            )
        )

    return sorted(fingerprint)


def _load_serialized_productos(value) -> list[dict]:
    if value is None or value == "":
        return []

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    return value if isinstance(value, list) else []


def _validar_permiso_costo_fabrica_override_creacion(
    current: Empleado,
    productos,
) -> None:
    if not _productos_tienen_costo_fabrica_override(productos):
        return

    current_role = infer_role(current.area, current.cargo)
    if current_role == "GERENCIA":
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Solo gerencia puede modificar el costo fabrica a nivel de "
            "cotizacion."
        ),
    )


def _validar_permiso_costo_fabrica_override_actualizacion(
    current: Empleado,
    productos_nuevos,
    productos_actuales,
) -> None:
    if not _productos_tienen_costo_fabrica_override(productos_nuevos):
        return

    current_role = infer_role(current.area, current.cargo)
    if current_role == "GERENCIA":
        return

    current_fingerprint = Counter(
        _build_productos_override_fingerprint(productos_actuales)
    )
    next_fingerprint = Counter(
        _build_productos_override_fingerprint(productos_nuevos)
    )

    if not (next_fingerprint - current_fingerprint):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Solo gerencia puede modificar el costo fabrica a nivel de "
            "cotizacion."
        ),
    )


def _resolver_jefe_aprobador(db: Session, empleado: Empleado) -> Empleado | None:
    jefe_id = getattr(empleado, "jefe_id", None)
    if not jefe_id:
        return None

    jefe = db.get(Empleado, jefe_id)
    if not jefe:
        return None

    if (jefe.estado or "").strip().lower() != "activo":
        return None

    return jefe


def _build_cotizacion_aprobacion_message(
    actor: Empleado,
    cotizacion: Cotizacion,
) -> str:
    titulo = (cotizacion.nombre_cotizacion or "").strip()
    if titulo:
        return (
            f"{actor.nombre} creo la cotizacion \"{titulo}\" "
            "y requiere tu aprobacion."
        )

    return f"{actor.nombre} creo la cotizacion #{cotizacion.id} y requiere tu aprobacion."


def _is_active_employee(empleado: Empleado) -> bool:
    estado = _normalize_team_lookup(getattr(empleado, "estado", None))
    return estado not in {"inactivo", "retirado", "bloqueado"}


def _is_warehouse_keeper(empleado: Empleado) -> bool:
    cargo = _normalize_team_lookup(getattr(empleado, "cargo", None))
    role = infer_role(getattr(empleado, "area", None), getattr(empleado, "cargo", None))
    return role == "LOGISTICA" and (
        "almacen" in cargo or "bodega" in cargo
    )


def _list_warehouse_keepers(db: Session, current: Empleado) -> list[Empleado]:
    empleados = list(db.execute(select(Empleado)).scalars().all())
    return [
        empleado
        for empleado in empleados
        if empleado.id != current.id
        and _is_active_employee(empleado)
        and _is_warehouse_keeper(empleado)
    ]


def _format_product_label(producto: Producto | None, product_id: int) -> str:
    if producto is None:
        return f"Producto #{product_id}"

    code = str(producto.codigo_producto or producto.referencia or "").strip()
    description = str(producto.descripcion or "").strip()
    label = " - ".join(part for part in (code, description) if part)
    return label or f"Producto #{product_id}"


def _safe_positive_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _build_stock_product_summary(db: Session, cotizacion: Cotizacion) -> str:
    productos_payload = _load_serialized_productos(cotizacion.productos)
    product_ids = sorted(
        {
            _safe_positive_int(item.get("id_producto"))
            for item in productos_payload
            if isinstance(item, dict)
        }
    )
    product_ids = [product_id for product_id in product_ids if product_id > 0]

    productos_by_id: dict[int, Producto] = {}
    if product_ids:
        productos = list(
            db.execute(select(Producto).where(Producto.id.in_(product_ids)))
            .scalars()
            .all()
        )
        apply_world_office_inventory(productos)
        productos_by_id = {producto.id: producto for producto in productos}

    inventory_lines: list[str] = []
    fallback_lines: list[str] = []

    for item in productos_payload:
        if not isinstance(item, dict):
            continue

        product_id = _safe_positive_int(item.get("id_producto"))
        if product_id <= 0:
            continue

        cantidad = max(1, _safe_positive_int(item.get("cantidad")))
        producto = productos_by_id.get(product_id)
        disponible = _safe_positive_int(
            getattr(producto, "cantidad_inventario", 0)
        )
        label = _format_product_label(producto, product_id)
        line = f"- {label}: cotizado {cantidad}, inventario disponible {disponible}"

        if _normalize_stage(item.get("tipo_importacion")) == "inventario":
            inventory_lines.append(line)
        elif disponible > 0:
            fallback_lines.append(line)

    selected_lines = inventory_lines or fallback_lines
    if not selected_lines:
        return (
            "No hay productos marcados como INVENTARIO ni existencias "
            "disponibles detectadas en el catalogo. Revisar detalle de la "
            "cotizacion antes de separar."
        )

    visible_lines = selected_lines[:8]
    if len(selected_lines) > len(visible_lines):
        visible_lines.append(f"- Y {len(selected_lines) - len(visible_lines)} producto(s) mas.")

    return "\n".join(visible_lines)


def _build_stock_notification_message(
    db: Session,
    cotizacion: Cotizacion,
    current: Empleado,
) -> str:
    return _build_stock_request_notification_message(db, cotizacion, current)


def _normalize_stock_status(value) -> str:
    normalized = _normalize_stage(value)
    return normalized if normalized in LOGISTICS_STOCK_STATUS_LABELS else "incompleto"


def _stock_status_label(value) -> str:
    return LOGISTICS_STOCK_STATUS_LABELS[_normalize_stock_status(value)]


def _has_stock_request_access(current: Empleado) -> bool:
    cargo = _normalize_team_lookup(current.cargo)
    return infer_role(current.area, current.cargo) == "GERENCIA" or has_view_permission(
        current,
        LOGISTICS_STOCK_REQUEST_PERMISSION,
    ) or (
        infer_role(current.area, current.cargo) == "LOGISTICA"
        and (
            "director" in cargo
            or "jefe" in cargo
            or "coordinador" in cargo
        )
    )


def _has_stock_update_access(current: Empleado) -> bool:
    return infer_role(current.area, current.cargo) == "GERENCIA" or has_view_permission(
        current,
        LOGISTICS_STOCK_UPDATE_PERMISSION,
    ) or _is_warehouse_keeper(current)


def _build_quote_label(cotizacion: Cotizacion) -> str:
    quote_title = str(cotizacion.nombre_cotizacion or "").strip()
    return f"#{cotizacion.id}" + (f" - {quote_title}" if quote_title else "")


def _build_stock_request_notification_message(
    db: Session,
    cotizacion: Cotizacion,
    current: Empleado,
) -> str:
    project_label = str(cotizacion.proyecto_nombre or "").strip()
    responsible = str(cotizacion.empleado_nombre or "").strip()

    parts = [
        f"{current.nombre} solicita verificar y separar stock para la cotizacion {_build_quote_label(cotizacion)}.",
        f"Estado actual: {_stock_status_label(cotizacion.logistica_stock_estado)}.",
    ]

    if project_label:
        parts.append(f"Proyecto: {project_label}.")

    if responsible:
        parts.append(f"Responsable comercial: {responsible}.")

    parts.append("Productos a revisar en inventario:")
    parts.append(_build_stock_product_summary(db, cotizacion))

    return "\n".join(parts)


def _build_stock_response_notification_message(
    db: Session,
    cotizacion: Cotizacion,
    current: Empleado,
    status_value: str,
) -> str:
    parts = [
        f"{current.nombre} actualizo el stock de la cotizacion {_build_quote_label(cotizacion)}.",
        f"Nuevo estado: {_stock_status_label(status_value)}.",
    ]

    if status_value == "parcial":
        parts.append("Ya hay unidades separadas o entregadas, pero aun falta completar.")
    elif status_value == "completo":
        parts.append("La totalidad de la mercancia ya esta separada o entregada.")
    else:
        parts.append("El stock sigue incompleto y requiere seguimiento.")

    parts.append("Resumen de inventario:")
    parts.append(_build_stock_product_summary(db, cotizacion))

    return "\n".join(parts)


def _create_or_reuse_stock_request_notifications(
    db: Session,
    *,
    cotizacion: Cotizacion,
    current: Empleado,
) -> None:
    recipients = _list_warehouse_keepers(db, current)
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron almacenistas activos para notificar.",
        )

    message = _build_stock_request_notification_message(db, cotizacion, current)
    recipient_ids = [recipient.id for recipient in recipients]
    existing_recipient_ids = set(
        db.execute(
            select(Notificacion.destinatario_empleado_id).where(
                Notificacion.destinatario_empleado_id.in_(recipient_ids),
                Notificacion.tipo == LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
                Notificacion.entidad_tipo == "cotizacion",
                Notificacion.entidad_id == cotizacion.id,
                Notificacion.resuelta_en.is_(None),
            )
        )
        .scalars()
        .all()
    )

    for recipient in recipients:
        if recipient.id in existing_recipient_ids:
            continue

        create_notification(
            db,
            destinatario_empleado_id=recipient.id,
            actor_empleado_id=current.id,
            tipo=LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
            area=current.area,
            titulo="Verificar stock de bodega",
            mensaje=message,
            entidad_tipo="cotizacion",
            entidad_id=cotizacion.id,
            ruta_destino=f"/logistica/cotizaciones?cotizacionId={cotizacion.id}",
            requiere_accion=True,
        )


def _list_stock_request_recipients(
    db: Session,
    current: Empleado,
    cotizacion_id: int,
) -> list[Empleado]:
    actor_ids = set(
        db.execute(
            select(Notificacion.actor_empleado_id).where(
                Notificacion.tipo == LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
                Notificacion.entidad_tipo == "cotizacion",
                Notificacion.entidad_id == cotizacion_id,
                Notificacion.actor_empleado_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )

    recipients = [
        empleado
        for empleado_id in actor_ids
        if empleado_id is not None
        for empleado in [db.get(Empleado, empleado_id)]
        if empleado is not None
        and empleado.id != current.id
        and _is_active_employee(empleado)
    ]

    if recipients:
        return recipients

    empleados = list(db.execute(select(Empleado)).scalars().all())
    return [
        empleado
        for empleado in empleados
        if empleado.id != current.id
        and _is_active_employee(empleado)
        and infer_role(empleado.area, empleado.cargo) == "LOGISTICA"
        and has_view_permission(empleado, LOGISTICS_STOCK_REQUEST_PERMISSION)
    ]


def _notify_stock_status_update(
    db: Session,
    *,
    cotizacion: Cotizacion,
    current: Empleado,
    status_value: str,
) -> None:
    recipients = _list_stock_request_recipients(db, current, cotizacion.id)
    if not recipients:
        return

    message = _build_stock_response_notification_message(
        db,
        cotizacion,
        current,
        status_value,
    )

    for recipient in recipients:
        create_notification(
            db,
            destinatario_empleado_id=recipient.id,
            actor_empleado_id=current.id,
            tipo=LOGISTICS_STOCK_RESPONSE_NOTIFICATION_TYPE,
            area=current.area,
            titulo=_stock_status_label(status_value),
            mensaje=message,
            entidad_tipo="cotizacion",
            entidad_id=cotizacion.id,
            ruta_destino=f"/logistica/cotizaciones?cotizacionId={cotizacion.id}",
            requiere_accion=status_value != "completo",
        )


def _quote_item_key(
    product_id: int,
    particion: int | None = None,
    nombre_particion: str | None = None,
) -> str:
    clean_particion = max(1, _safe_positive_int(particion) or 1)
    clean_name = " ".join(str(nombre_particion or "").strip().split()).upper()
    return f"{product_id}:{clean_particion}:{clean_name}"


def _load_logistics_quote_items(
    db: Session,
    cotizacion: Cotizacion,
) -> tuple[dict[str, dict], dict[int, Producto]]:
    payload = _load_serialized_productos(cotizacion.productos)
    items_by_key: dict[str, dict] = {}

    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue

        product_id = _safe_positive_int(raw_item.get("id_producto"))
        cantidad = _safe_positive_int(raw_item.get("cantidad"))
        if product_id <= 0 or cantidad <= 0:
            continue

        particion = max(1, _safe_positive_int(raw_item.get("particion")) or 1)
        nombre_particion = str(raw_item.get("nombre_particion") or "").strip() or None
        item_key = _quote_item_key(product_id, particion, nombre_particion)
        existing = items_by_key.get(item_key)

        if existing:
            existing["cantidad_cotizada"] += cantidad
            continue

        items_by_key[item_key] = {
            "item_key": item_key,
            "id_producto": product_id,
            "particion": particion,
            "nombre_particion": nombre_particion,
            "tipo_importacion": raw_item.get("tipo_importacion"),
            "cantidad_cotizada": cantidad,
        }

    product_ids = sorted({item["id_producto"] for item in items_by_key.values()})
    products_by_id: dict[int, Producto] = {}
    if product_ids:
        products = list(
            db.execute(select(Producto).where(Producto.id.in_(product_ids)))
            .scalars()
            .all()
        )
        apply_world_office_inventory(products)
        products_by_id = {product.id: product for product in products}

    return items_by_key, products_by_id


def _load_separations_by_key(
    db: Session,
    cotizacion_id: int,
) -> dict[str, CotizacionLogisticaSeparacion]:
    rows = list(
        db.execute(
            select(CotizacionLogisticaSeparacion).where(
                CotizacionLogisticaSeparacion.cotizacion_id == cotizacion_id
            )
        )
        .scalars()
        .all()
    )
    return {row.item_key: row for row in rows}


def _load_delivered_by_key(db: Session, cotizacion_id: int) -> dict[str, int]:
    rows = list(
        db.execute(
            select(CotizacionLogisticaRemisionItem).where(
                CotizacionLogisticaRemisionItem.cotizacion_id == cotizacion_id
            )
        )
        .scalars()
        .all()
    )
    delivered_by_key: dict[str, int] = {}
    for row in rows:
        delivered_by_key[row.item_key] = delivered_by_key.get(row.item_key, 0) + int(
            row.cantidad or 0
        )
    return delivered_by_key


def _product_payload(product: Producto | None) -> dict:
    if product is None:
        return {
            "codigo_producto": None,
            "descripcion": None,
            "marca": None,
            "cantidad_inventario": 0,
        }

    return {
        "codigo_producto": product.codigo_producto or product.referencia,
        "descripcion": product.descripcion,
        "marca": product.marca,
        "cantidad_inventario": _safe_positive_int(product.cantidad_inventario),
    }


def _stock_status_from_progress(total: int, separated: int, delivered: int) -> str:
    if total <= 0:
        return "incompleto"

    progress = delivered if delivered > 0 else separated
    if progress >= total:
        return "completo"
    if progress > 0:
        return "parcial"
    return "incompleto"


def _build_logistics_remisiones_payload(
    db: Session,
    cotizacion_id: int,
    items_by_key: dict[str, dict],
    products_by_id: dict[int, Producto],
) -> list[dict]:
    remisiones = list(
        db.execute(
            select(CotizacionLogisticaRemision)
            .where(CotizacionLogisticaRemision.cotizacion_id == cotizacion_id)
            .order_by(
                CotizacionLogisticaRemision.fecha_entrega.desc(),
                CotizacionLogisticaRemision.id.desc(),
            )
        )
        .scalars()
        .all()
    )

    payload: list[dict] = []
    for remision in remisiones:
        item_payload: list[dict] = []
        for item in remision.items:
            quote_item = items_by_key.get(item.item_key, {})
            product = products_by_id.get(item.id_producto)
            product_data = _product_payload(product)
            item_payload.append(
                {
                    "item_key": item.item_key,
                    "id_producto": item.id_producto,
                    "codigo_producto": product_data["codigo_producto"],
                    "descripcion": product_data["descripcion"],
                    "marca": product_data["marca"],
                    "particion": item.particion,
                    "nombre_particion": (
                        item.nombre_particion
                        or quote_item.get("nombre_particion")
                    ),
                    "cantidad": item.cantidad,
                }
            )

        payload.append(
            {
                "id": remision.id,
                "numero_remision": remision.numero_remision,
                "fecha_entrega": remision.fecha_entrega,
                "observaciones": remision.observaciones,
                "creado_en": remision.creado_en,
                "creado_por_id": remision.creado_por_id,
                "items": item_payload,
            }
        )

    return payload


def _build_logistics_summary(db: Session, cotizacion: Cotizacion) -> dict:
    items_by_key, products_by_id = _load_logistics_quote_items(db, cotizacion)
    separations_by_key = _load_separations_by_key(db, cotizacion.id)
    delivered_by_key = _load_delivered_by_key(db, cotizacion.id)

    products_payload: list[dict] = []
    total_units = 0
    separated_units = 0
    delivered_units = 0

    for item_key, item in items_by_key.items():
        product = products_by_id.get(item["id_producto"])
        product_data = _product_payload(product)
        separation = separations_by_key.get(item_key)
        quoted = int(item["cantidad_cotizada"])
        separated = _safe_positive_int(
            separation.cantidad_separada if separation else 0
        )
        delivered = _safe_positive_int(delivered_by_key.get(item_key))
        pending = max(0, quoted - delivered)
        deliverable = max(0, separated - delivered)

        total_units += quoted
        separated_units += min(separated, quoted)
        delivered_units += min(delivered, quoted)

        products_payload.append(
            {
                "item_key": item_key,
                "id_producto": item["id_producto"],
                "codigo_producto": product_data["codigo_producto"],
                "descripcion": product_data["descripcion"],
                "marca": product_data["marca"],
                "particion": item["particion"],
                "nombre_particion": item["nombre_particion"],
                "tipo_importacion": item["tipo_importacion"],
                "cantidad_cotizada": quoted,
                "cantidad_inventario": product_data["cantidad_inventario"],
                "cantidad_separada": separated,
                "cantidad_entregada": delivered,
                "cantidad_pendiente": pending,
                "cantidad_por_entregar": deliverable,
                "porcentaje_entregado": (
                    round((min(delivered, quoted) / quoted) * 100, 2)
                    if quoted > 0
                    else 0
                ),
                "observaciones_separacion": (
                    separation.observaciones if separation else None
                ),
            }
        )

    status_value = _stock_status_from_progress(
        total_units,
        separated_units,
        delivered_units,
    )
    progress_units = delivered_units if delivered_units > 0 else separated_units
    percentage = (
        round((min(progress_units, total_units) / total_units) * 100, 2)
        if total_units > 0
        else 0
    )

    purchase_groups: dict[str, dict] = {}
    for product_payload in products_payload:
        missing_from_stock = max(
            0,
            int(product_payload["cantidad_cotizada"])
            - int(product_payload["cantidad_separada"]),
        )
        if missing_from_stock <= 0:
            continue

        brand = str(product_payload.get("marca") or "SIN MARCA").strip() or "SIN MARCA"
        group = purchase_groups.setdefault(
            brand,
            {
                "marca": brand,
                "unidades_pendientes": 0,
                "productos": [],
            },
        )
        group["unidades_pendientes"] += missing_from_stock
        group_product = {**product_payload, "cantidad_pendiente": missing_from_stock}
        group["productos"].append(group_product)

    return {
        "cotizacion_id": cotizacion.id,
        "stock_estado": status_value,
        "porcentaje_stock": percentage,
        "total_unidades": total_units,
        "unidades_separadas": separated_units,
        "unidades_entregadas": delivered_units,
        "unidades_pendientes": max(0, total_units - delivered_units),
        "productos": products_payload,
        "remisiones": _build_logistics_remisiones_payload(
            db,
            cotizacion.id,
            items_by_key,
            products_by_id,
        ),
        "ordenes_compra_sugeridas": list(purchase_groups.values()),
    }


def _sync_logistics_progress_fields(cotizacion: Cotizacion, summary: dict) -> bool:
    previous_status = _normalize_stock_status(cotizacion.logistica_stock_estado)
    next_status = _normalize_stock_status(summary.get("stock_estado"))
    cotizacion.logistica_stock_estado = next_status
    cotizacion.logistica_stock = int(round(float(summary.get("porcentaje_stock") or 0)))
    cotizacion.logistica_unidades_pendientes = int(
        summary.get("unidades_pendientes") or 0
    )
    return previous_status != next_status


def _require_approved_logistics_cotizacion(
    db: Session,
    cotizacion_id: int,
) -> CotizacionAprobada:
    approved = db.get(CotizacionAprobada, cotizacion_id)
    if approved is not None:
        _set_cotizacion_responsable_name(
            approved,
            db.get(Empleado, approved.id_empleado),
        )
        return approved

    cotizacion = crud_cotizacion.get(db, cotizacion_id)
    if cotizacion is None:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    if not _is_approved_status(cotizacion.estado):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion debe estar aprobada para gestion logistica.",
        )

    approved = _sync_cotizacion_aprobada_from_cotizacion(db, cotizacion)
    if approved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion debe estar aprobada para gestion logistica.",
        )

    db.flush()
    _set_cotizacion_responsable_name(
        approved,
        db.get(Empleado, approved.id_empleado),
    )
    return approved


def _validate_separation_inventory(
    items_by_key: dict[str, dict],
    products_by_id: dict[int, Producto],
    next_separated_by_key: dict[str, int],
) -> None:
    separated_by_product: dict[int, int] = {}
    for item_key, item in items_by_key.items():
        product_id = int(item["id_producto"])
        separated_by_product[product_id] = separated_by_product.get(product_id, 0) + int(
            next_separated_by_key.get(item_key, 0)
        )

    for product_id, separated in separated_by_product.items():
        product = products_by_id.get(product_id)
        available = _safe_positive_int(
            getattr(product, "cantidad_inventario", 0) if product else 0
        )
        if separated > available:
            label = _format_product_label(product, product_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No puedes separar {separated} unidad(es) de {label}; "
                    f"el inventario disponible es {available}."
                ),
            )


def _next_remision_number(db: Session, cotizacion_id: int) -> str:
    count = db.execute(
        select(func.count(CotizacionLogisticaRemision.id)).where(
            CotizacionLogisticaRemision.cotizacion_id == cotizacion_id
        )
    ).scalar_one()
    return f"REM-COT{cotizacion_id}-{int(count or 0) + 1:03d}"


def _build_quote_document_base_name(
    cotizacion_id: int | None,
    tipo_servicio: str | None,
    nombre_proyecto: str | None,
    cliente_nombre: str | None,
) -> str:
    service_label = _service_label(tipo_servicio)
    type_block = f"COT {service_label} INGEAR" if service_label else "COT INGEAR"
    project_name = _sanitize_filename_segment(
        nombre_proyecto,
        "SIN NOMBRE DE PROYECTO",
    ).upper()
    client_name = _sanitize_filename_segment(cliente_nombre, "SIN CLIENTE").upper()
    id_label = _sanitize_filename_segment(
        str(cotizacion_id) if cotizacion_id else None,
        "PENDIENTE",
    )

    return f"{id_label} - {type_block} - {project_name} - {client_name}"


def _build_quote_document_filename(
    cotizacion_id: int | None,
    tipo_servicio: str | None,
    nombre_proyecto: str | None,
    cliente_nombre: str | None,
    extension: str | None = "pdf",
) -> str:
    base_name = _build_quote_document_base_name(
        cotizacion_id=cotizacion_id,
        tipo_servicio=tipo_servicio,
        nombre_proyecto=nombre_proyecto,
        cliente_nombre=cliente_nombre,
    )
    safe_extension = _normalize_extension(extension)
    return f"{base_name}.{safe_extension}"


def _build_oportunidad_cotizaciones_value(
    cotizacion: Cotizacion,
    oportunidad: Oportunidad | None,
) -> str:
    cliente_nombre = getattr(getattr(oportunidad, "cliente", None), "razon_social", None)

    return _build_quote_document_filename(
        cotizacion_id=cotizacion.id,
        tipo_servicio=cotizacion.tipo_servicio or getattr(oportunidad, "tipo_servicio", None),
        nombre_proyecto=getattr(oportunidad, "nombre_proyecto", None),
        cliente_nombre=cliente_nombre,
        extension="xlsx",
    )


def _split_cotizaciones_entries(value: str | None) -> list[str]:
    seen: set[str] = set()
    entries: list[str] = []

    normalized_text = str(value or "").replace("\r", "\n")
    for raw_entry in normalized_text.split("\n"):
        entry = raw_entry.strip()
        if not entry or entry in seen:
            continue
        seen.add(entry)
        entries.append(entry)

    return entries


def _join_cotizaciones_entries(entries: list[str]) -> str | None:
    clean_entries = [entry.strip() for entry in entries if entry and entry.strip()]
    return "\n".join(clean_entries) if clean_entries else None


def _upsert_cotizaciones_value(
    current_text: str | None,
    next_entry: str,
    *,
    previous_entry: str | None = None,
) -> str:
    normalized_previous = (previous_entry or "").strip()
    normalized_next = next_entry.strip()
    base_entries: list[str] = []

    for entry in _split_cotizaciones_entries(current_text):
        if normalized_previous and entry == normalized_previous:
            continue
        if entry == normalized_next:
            continue
        base_entries.append(entry)

    base_entries.append(normalized_next)
    return _join_cotizaciones_entries(base_entries) or normalized_next


def _remove_cotizaciones_entry(
    current_text: str | None,
    entry_to_remove: str | None,
) -> str | None:
    normalized_remove = (entry_to_remove or "").strip()
    if not normalized_remove:
        return _join_cotizaciones_entries(_split_cotizaciones_entries(current_text))

    filtered_entries = [
        entry
        for entry in _split_cotizaciones_entries(current_text)
        if entry != normalized_remove
    ]
    return _join_cotizaciones_entries(filtered_entries)


def _find_existing_proyecto_for_oportunidad(
    db: Session,
    oportunidad_id: int,
) -> Proyecto | None:
    stmt = (
        select(Proyecto)
        .where(Proyecto.oportunidad_id == oportunidad_id)
        .order_by(Proyecto.id.asc())
    )
    return db.execute(stmt).scalars().first()


def _sync_oportunidad_cotizaciones(
    db: Session,
    cotizacion: Cotizacion,
    *,
    fecha_probable_venta: date | None = None,
    previous_oportunidad_id: int | None = None,
    previous_cotizaciones_value: str | None = None,
) -> Oportunidad:
    oportunidad_id = cotizacion.id_oportunidad
    if not oportunidad_id:
        raise HTTPException(
            status_code=400,
            detail="La cotizacion debe estar ligada a una oportunidad.",
        )

    oportunidad = db.get(Oportunidad, oportunidad_id)
    if not oportunidad:
        raise HTTPException(
            status_code=400,
            detail="La oportunidad asociada a la cotizacion no existe.",
        )

    next_cotizacion_value = _build_oportunidad_cotizaciones_value(
        cotizacion,
        oportunidad,
    )
    same_oportunidad = previous_oportunidad_id == oportunidad_id
    oportunidad.cotizaciones = _upsert_cotizaciones_value(
        oportunidad.cotizaciones,
        next_cotizacion_value,
        previous_entry=previous_cotizaciones_value if same_oportunidad else None,
    )

    fecha_envio = (
        cotizacion.fecha_creacion.date()
        if getattr(cotizacion, "fecha_creacion", None) is not None
        else date.today()
    )

    if oportunidad.fecha_cotizacion is None:
        oportunidad.fecha_cotizacion = fecha_envio

    if oportunidad.fecha_cierre is None and fecha_probable_venta is not None:
        oportunidad.fecha_cierre = fecha_probable_venta

    sync_oportunidad_rubro_sin_iva(db, oportunidad_id)

    if previous_oportunidad_id and previous_oportunidad_id != oportunidad_id:
        oportunidad_anterior = db.get(Oportunidad, previous_oportunidad_id)
        if oportunidad_anterior:
            oportunidad_anterior.cotizaciones = _remove_cotizaciones_entry(
                oportunidad_anterior.cotizaciones,
                previous_cotizaciones_value,
            )
            sync_oportunidad_rubro_sin_iva(db, previous_oportunidad_id)

    return oportunidad


@router.get("/", response_model=list[CotizacionOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    rows = crud_cotizacion.list(db, skip=skip, limit=limit)
    return _annotate_cotizacion_permissions(db, current, rows)


@router.get("/aprobadas", response_model=list[CotizacionOut])
def listar_aprobadas(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_aprobada_access),
):
    stmt = (
        select(CotizacionAprobada)
        .order_by(CotizacionAprobada.id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars().all())
    return _annotate_cotizacion_permissions(db, current, rows)


@router.get("/{cotizacion_id}", response_model=CotizacionOut)
def obtener(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return _annotate_cotizacion_permissions(db, current, obj)


@router.put("/{cotizacion_id}/logistica", response_model=CotizacionOut)
def actualizar_logistica(
    cotizacion_id: int,
    payload: CotizacionLogisticaUpdate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_aprobada_access),
):
    obj = _require_approved_logistics_cotizacion(db, cotizacion_id)

    previous_stock_status = _normalize_stock_status(obj.logistica_stock_estado)
    data = payload.model_dump(exclude_unset=True)

    if "logistica_stock_estado" in data:
        if not _has_stock_update_access(current):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el almacenista puede actualizar el estado de stock.",
            )

        data["logistica_stock_estado"] = _normalize_stock_status(
            data.get("logistica_stock_estado")
        )

    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(obj, key, value)

    if "logistica_stock_estado" in data:
        next_stock_status = _normalize_stock_status(obj.logistica_stock_estado)
        _set_cotizacion_responsable_name(obj, db.get(Empleado, obj.id_empleado))

        if next_stock_status != previous_stock_status:
            if next_stock_status == "completo":
                resolve_notifications_for_entity(
                    db,
                    entidad_tipo="cotizacion",
                    entidad_id=obj.id,
                    tipo=LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
                )

            _notify_stock_status_update(
                db,
                cotizacion=obj,
                current=current,
                status_value=next_stock_status,
            )

    db.commit()
    db.refresh(obj)
    return _annotate_cotizacion_permissions(db, current, obj)


@router.get(
    "/{cotizacion_id}/logistica/detalle",
    response_model=CotizacionLogisticaResumenOut,
)
def obtener_detalle_logistica(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_aprobada_access),
):
    cotizacion = _require_approved_logistics_cotizacion(db, cotizacion_id)
    return _build_logistics_summary(db, cotizacion)


@router.put(
    "/{cotizacion_id}/logistica/separacion",
    response_model=CotizacionLogisticaResumenOut,
)
def actualizar_separacion_logistica(
    cotizacion_id: int,
    payload: CotizacionLogisticaSeparacionIn,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_aprobada_access),
):
    if not _has_stock_update_access(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el almacenista puede marcar productos separados.",
        )

    cotizacion = _require_approved_logistics_cotizacion(db, cotizacion_id)
    items_by_key, products_by_id = _load_logistics_quote_items(db, cotizacion)
    if not items_by_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion no tiene productos para separar.",
        )

    separations_by_key = _load_separations_by_key(db, cotizacion.id)
    delivered_by_key = _load_delivered_by_key(db, cotizacion.id)
    next_separated_by_key = {
        item_key: _safe_positive_int(separation.cantidad_separada)
        for item_key, separation in separations_by_key.items()
        if item_key in items_by_key
    }

    requested_updates = {item.item_key: item for item in payload.items}
    for item_key, item in requested_updates.items():
        quote_item = items_by_key.get(item_key)
        if quote_item is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El producto {item_key} no pertenece a la cotizacion.",
            )

        quoted = int(quote_item["cantidad_cotizada"])
        delivered = _safe_positive_int(delivered_by_key.get(item_key))
        if item.cantidad_separada > quoted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "La cantidad separada no puede superar la cantidad "
                    f"cotizada ({quoted}) para el producto {item_key}."
                ),
            )

        if item.cantidad_separada < delivered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "La cantidad separada no puede ser menor que la cantidad "
                    f"ya remisionada ({delivered}) para el producto {item_key}."
                ),
            )

        next_separated_by_key[item_key] = item.cantidad_separada

    _validate_separation_inventory(
        items_by_key,
        products_by_id,
        next_separated_by_key,
    )

    for item_key, item in requested_updates.items():
        quote_item = items_by_key[item_key]
        separation = separations_by_key.get(item_key)
        if separation is None:
            separation = CotizacionLogisticaSeparacion(
                cotizacion_id=cotizacion.id,
                item_key=item_key,
                id_producto=quote_item["id_producto"],
                creado_por_id=current.id,
            )
            db.add(separation)

        separation.particion = quote_item["particion"]
        separation.nombre_particion = quote_item["nombre_particion"]
        separation.cantidad_cotizada = quote_item["cantidad_cotizada"]
        separation.cantidad_separada = item.cantidad_separada
        separation.observaciones = (item.observaciones or "").strip() or None
        separation.actualizado_por_id = current.id

    summary = _build_logistics_summary(db, cotizacion)
    status_changed = _sync_logistics_progress_fields(cotizacion, summary)
    if status_changed:
        if cotizacion.logistica_stock_estado == "completo":
            resolve_notifications_for_entity(
                db,
                entidad_tipo="cotizacion",
                entidad_id=cotizacion.id,
                tipo=LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
            )
        _notify_stock_status_update(
            db,
            cotizacion=cotizacion,
            current=current,
            status_value=cotizacion.logistica_stock_estado,
        )

    db.commit()
    db.refresh(cotizacion)
    return _build_logistics_summary(db, cotizacion)


@router.post(
    "/{cotizacion_id}/logistica/remisiones",
    response_model=CotizacionLogisticaResumenOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_remision_logistica(
    cotizacion_id: int,
    payload: CotizacionLogisticaRemisionCreate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_aprobada_access),
):
    if not _has_stock_update_access(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el almacenista puede generar remisiones logisticas.",
        )

    cotizacion = _require_approved_logistics_cotizacion(db, cotizacion_id)
    items_by_key, _products_by_id = _load_logistics_quote_items(db, cotizacion)
    if not items_by_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion no tiene productos para remisionar.",
        )

    separations_by_key = _load_separations_by_key(db, cotizacion.id)
    delivered_by_key = _load_delivered_by_key(db, cotizacion.id)
    quantities_by_key: dict[str, int] = {}
    for item in payload.items:
        quantities_by_key[item.item_key] = (
            quantities_by_key.get(item.item_key, 0) + item.cantidad
        )

    for item_key, quantity in quantities_by_key.items():
        quote_item = items_by_key.get(item_key)
        if quote_item is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El producto {item_key} no pertenece a la cotizacion.",
            )

        quoted = int(quote_item["cantidad_cotizada"])
        already_delivered = _safe_positive_int(delivered_by_key.get(item_key))
        separated = _safe_positive_int(
            separations_by_key.get(item_key).cantidad_separada
            if separations_by_key.get(item_key)
            else 0
        )

        if already_delivered + quantity > quoted:
            pending = max(0, quoted - already_delivered)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No puedes remisionar {quantity} unidad(es) de {item_key}; "
                    f"solo quedan {pending} pendiente(s) de la cotizacion."
                ),
            )

        if already_delivered + quantity > separated:
            available = max(0, separated - already_delivered)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No puedes remisionar {quantity} unidad(es) de {item_key}; "
                    f"solo hay {available} unidad(es) separadas sin entregar."
                ),
            )

    numero_remision = (
        (payload.numero_remision or "").strip()
        or _next_remision_number(db, cotizacion.id)
    )
    duplicate = db.execute(
        select(CotizacionLogisticaRemision.id).where(
            CotizacionLogisticaRemision.cotizacion_id == cotizacion.id,
            CotizacionLogisticaRemision.numero_remision == numero_remision,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una remision con ese numero para esta cotizacion.",
        )

    remision = CotizacionLogisticaRemision(
        cotizacion_id=cotizacion.id,
        numero_remision=numero_remision,
        fecha_entrega=payload.fecha_entrega,
        observaciones=(payload.observaciones or "").strip() or None,
        creado_por_id=current.id,
    )
    db.add(remision)
    db.flush()

    for item_key, quantity in quantities_by_key.items():
        quote_item = items_by_key[item_key]
        db.add(
            CotizacionLogisticaRemisionItem(
                remision_id=remision.id,
                cotizacion_id=cotizacion.id,
                item_key=item_key,
                id_producto=quote_item["id_producto"],
                particion=quote_item["particion"],
                nombre_particion=quote_item["nombre_particion"],
                cantidad=quantity,
            )
        )

    summary = _build_logistics_summary(db, cotizacion)
    _sync_logistics_progress_fields(cotizacion, summary)
    if cotizacion.logistica_stock_estado == "completo":
        resolve_notifications_for_entity(
            db,
            entidad_tipo="cotizacion",
            entidad_id=cotizacion.id,
            tipo=LOGISTICS_STOCK_REQUEST_NOTIFICATION_TYPE,
        )
    _notify_stock_status_update(
        db,
        cotizacion=cotizacion,
        current=current,
        status_value=cotizacion.logistica_stock_estado,
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No fue posible crear la remision.",
        )

    db.refresh(cotizacion)
    return _build_logistics_summary(db, cotizacion)


@router.post("/{cotizacion_id}/logistica/solicitar-stock", response_model=CotizacionOut)
def solicitar_verificacion_stock(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_aprobada_access),
):
    if not _has_stock_request_access(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el director logistico puede solicitar verificacion de stock.",
        )

    obj = _require_approved_logistics_cotizacion(db, cotizacion_id)

    if not obj.logistica_stock_estado:
        obj.logistica_stock_estado = "incompleto"

    _create_or_reuse_stock_request_notifications(
        db,
        cotizacion=obj,
        current=current,
    )

    db.commit()
    db.refresh(obj)
    return _annotate_cotizacion_permissions(db, current, obj)


@router.post("/", response_model=CotizacionOut, status_code=201)
def crear(
    payload: CotizacionCreate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    data = payload.model_dump()
    fecha_probable_venta = data.pop("fecha_probable_venta", None)
    _validar_permiso_costo_fabrica_override_creacion(current, data["productos"])
    _validar_productos_existentes(db, data["productos"])
    data["productos"] = _serialize_productos(data["productos"])
    data["id_empleado"] = current.id

    jefe_aprobador = _resolver_jefe_aprobador(db, current)
    data["estado"] = "1" if jefe_aprobador else "2"

    try:
        cotizacion = Cotizacion(**data)
        db.add(cotizacion)
        db.flush()
        _sync_oportunidad_cotizaciones(
            db,
            cotizacion,
            fecha_probable_venta=fecha_probable_venta,
        )

        if jefe_aprobador:
            create_notification(
                db,
                destinatario_empleado_id=jefe_aprobador.id,
                actor_empleado_id=current.id,
                tipo="cotizacion.aprobacion_requerida",
                area=current.area,
                titulo="Cotizacion pendiente de aprobacion",
                mensaje=_build_cotizacion_aprobacion_message(current, cotizacion),
                entidad_tipo="cotizacion",
                entidad_id=cotizacion.id,
                ruta_destino=f"/cotizador?cotizacionId={cotizacion.id}&approval=1",
                requiere_accion=True,
            )
        else:
            _sync_cotizacion_aprobada_from_cotizacion(db, cotizacion)

        db.commit()
        db.refresh(cotizacion)
        _set_cotizacion_responsable_name(cotizacion, current)
        setattr(cotizacion, "can_edit", True)
        setattr(cotizacion, "can_duplicate", True)
        return cotizacion
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No fue posible crear la cotizacion.",
        )


@router.put("/{cotizacion_id}", response_model=CotizacionOut)
def actualizar(
    cotizacion_id: int,
    payload: CotizacionUpdate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    _assert_can_edit_cotizacion(db, current, obj)

    data = payload.model_dump(exclude_unset=True)
    # El propietario/asesor de una cotizacion no debe cambiar por editarla
    # desde otra cuenta con permisos.
    data.pop("id_empleado", None)
    fecha_probable_venta = data.pop("fecha_probable_venta", None)
    crear_proyecto_ganada = bool(data.pop("crear_proyecto_ganada", False))
    if "productos" in data:
        _validar_permiso_costo_fabrica_override_actualizacion(
            current,
            data["productos"],
            _load_serialized_productos(obj.productos),
        )
        _validar_productos_existentes(db, data["productos"])
        data["productos"] = _serialize_productos(data["productos"])

    oportunidad_anterior_id = obj.id_oportunidad
    oportunidad_anterior = (
        db.get(Oportunidad, oportunidad_anterior_id)
        if oportunidad_anterior_id
        else None
    )
    cotizacion_anterior_en_oportunidad = (
        _build_oportunidad_cotizaciones_value(obj, oportunidad_anterior)
        if oportunidad_anterior
        else None
    )
    etapa_anterior = obj.etapa_cotizacion
    etapa_siguiente = data.get("etapa_cotizacion", obj.etapa_cotizacion)

    if crear_proyecto_ganada and (
        _is_won_stage(etapa_anterior) or not _is_won_stage(etapa_siguiente)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Solo se puede crear un proyecto cuando la etapa de la "
                "cotizacion cambia a Ganada."
            ),
        )

    proyecto = None
    proyecto_creado_id = None

    try:
        obj = crud_cotizacion.update(db, obj, data, commit=False)

        if crear_proyecto_ganada:
            oportunidad_id = obj.id_oportunidad
            if not oportunidad_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "La cotizacion debe estar ligada a una oportunidad para "
                        "crear el proyecto."
                    ),
                )

            oportunidad = db.get(Oportunidad, oportunidad_id)
            if not oportunidad:
                raise HTTPException(
                    status_code=400,
                    detail="La oportunidad asociada a la cotizacion no existe.",
                )

            proyecto_existente = _find_existing_proyecto_for_oportunidad(
                db,
                oportunidad.id,
            )
            if proyecto_existente is None:
                nombre_proyecto = (oportunidad.nombre_proyecto or "").strip()
                if not nombre_proyecto:
                    raise HTTPException(
                        status_code=400,
                        detail="La oportunidad asociada no tiene nombre de proyecto.",
                    )

                proyecto = Proyecto(
                    nombre=nombre_proyecto,
                    oportunidad_id=oportunidad.id,
                )
                db.add(proyecto)

        _sync_oportunidad_cotizaciones(
            db,
            obj,
            fecha_probable_venta=fecha_probable_venta,
            previous_oportunidad_id=oportunidad_anterior_id,
            previous_cotizaciones_value=cotizacion_anterior_en_oportunidad,
        )
        _sync_cotizacion_aprobada_from_cotizacion(db, obj)

        db.commit()
        db.refresh(obj)
        if proyecto is not None:
            db.refresh(proyecto)
            proyecto_creado_id = proyecto.id
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible actualizar la cotizacion.",
        )

    setattr(obj, "proyecto_creado_id", proyecto_creado_id)
    _set_cotizacion_responsable_name(obj, db.get(Empleado, obj.id_empleado))
    setattr(obj, "can_edit", True)
    setattr(obj, "can_duplicate", True)
    return obj


@router.delete("/{cotizacion_id}", status_code=204)
def eliminar(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    _assert_can_edit_cotizacion(db, current, obj)

    oportunidad_id = obj.id_oportunidad
    oportunidad = db.get(Oportunidad, oportunidad_id) if oportunidad_id else None
    cotizacion_en_oportunidad = (
        _build_oportunidad_cotizaciones_value(obj, oportunidad)
        if oportunidad
        else None
    )

    try:
        db.delete(obj)
        if oportunidad:
            oportunidad.cotizaciones = _remove_cotizaciones_entry(
                oportunidad.cotizaciones,
                cotizacion_en_oportunidad,
            )
        db.flush()
        sync_oportunidad_rubro_sin_iva(db, oportunidad_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible eliminar la cotizacion.",
        )

    return None


@router.post("/{cotizacion_id}/aprobar", response_model=CotizacionOut)
def aprobar(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(get_current_empleado),
):
    cotizacion = crud_cotizacion.get(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    jefe_id = getattr(cotizacion.empleado, "jefe_id", None)
    current_role = infer_role(current.area, current.cargo)
    can_approve = current.id == jefe_id or current_role == "GERENCIA"

    if not can_approve:
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para aprobar esta cotizacion.",
        )

    if (cotizacion.estado or "").strip() != "2":
        cotizacion.estado = "2"

    _sync_cotizacion_aprobada_from_cotizacion(db, cotizacion)

    resolve_notifications_for_entity(
        db,
        entidad_tipo="cotizacion",
        entidad_id=cotizacion.id,
        tipo="cotizacion.aprobacion_requerida",
        destinatario_empleado_id=current.id if current.id == jefe_id else None,
    )
    db.commit()
    db.refresh(cotizacion)
    _set_cotizacion_responsable_name(cotizacion, cotizacion.empleado)
    setattr(cotizacion, "can_edit", True)
    setattr(cotizacion, "can_duplicate", True)
    return cotizacion

@router.get("/{cotizacion_id}/versiones", response_model=list[CotizacionVersionOut])
def listar_versiones(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return crud_cotizacion.list_versions(db, cotizacion_id)


@router.get("/{cotizacion_id}/versiones/{numero_version}", response_model=CotizacionVersionOut)
def obtener_version(
    cotizacion_id: int,
    numero_version: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    version = crud_cotizacion.get_version(db, cotizacion_id, numero_version)
    if not version:
        raise HTTPException(status_code=404, detail="Version de cotizacion no encontrada")

    return version



def _clean_email(value: str | None, label: str) -> str:
    email = (value or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} no tiene un correo valido.",
        )
    return email


def _normalize_lookup(value: str | None) -> str:
    return (
        unicodedata.normalize("NFD", (value or "").strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _sanitize_filename_segment(value: str | None, fallback: str) -> str:
    cleaned = "".join(
        " " if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch
        for ch in (value or "")
    )
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned or fallback


def _service_label(value: str | None) -> str:
    normalized = _normalize_lookup(value)

    if not normalized:
        return ""
    if "ilumin" in normalized:
        return "ILUM"
    if "control" in normalized:
        return "CONTROL"
    if "instal" in normalized:
        return "INSTALACIÓN"
    if "manten" in normalized:
        return "MANTENIMIENTO"
    if "dise" in normalized:
        return "DISEÑO"

    return _sanitize_filename_segment(value.upper() if value else "", "GENERAL")


def _default_pdf_filename(cotizacion) -> str:
    return _build_quote_document_filename(
        cotizacion_id=cotizacion.id,
        tipo_servicio=(
            cotizacion.tipo_servicio
            or getattr(cotizacion.oportunidad, "tipo_servicio", None)
        ),
        nombre_proyecto=getattr(cotizacion.oportunidad, "nombre_proyecto", None),
        cliente_nombre=getattr(
            getattr(cotizacion.oportunidad, "cliente", None),
            "razon_social",
            None,
        ),
        extension="pdf",
    )


def _safe_pdf_filename(value: str | None, cotizacion) -> str:
    filename = (value or "").strip() or _default_pdf_filename(cotizacion)
    filename = filename.replace("\r", "").replace("\n", "")
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    return filename


def _default_subject(cotizacion_id: int, nombre_cotizacion: str | None) -> str:
    nombre = (nombre_cotizacion or "").strip()
    return f"Cotizacion IngeAr #{cotizacion_id}" if not nombre else f"IngeAr | {nombre}"


def _default_body(sender_name: str, sender_role: str | None, nombre_cotizacion: str | None) -> str:
    nombre = (nombre_cotizacion or "").strip() or "cotizacion solicitada"
    cargo = (sender_role or "").strip()
    firma = sender_name if not cargo else f"{sender_name}\n{cargo}"
    return (
        f"Hola,\n\n"
        f"Adjunto enviamos la {nombre} en formato PDF.\n\n"
        f"Quedamos atentos a cualquier comentario.\n\n"
        f"{firma}\n"
        f"IngeAr"
    )


@router.post("/{cotizacion_id}/enviar-email", response_model=CotizacionEmailOut)
def enviar_email_cotizacion(
    cotizacion_id: int,
    payload: CotizacionEmailIn,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    cotizacion = crud_cotizacion.get(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    if not cotizacion.oportunidad or not cotizacion.oportunidad.cliente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion no tiene cliente asociado.",
        )

    sender_email = _clean_email(current.email, "El empleado autenticado")
    to_email = _clean_email(
        payload.to_email or cotizacion.oportunidad.cliente.email,
        "El cliente asociado",
    )

    pdf_bytes = decode_pdf_base64(payload.pdf_base64)
    pdf_filename = _safe_pdf_filename(payload.pdf_filename, cotizacion)
    subject = (payload.subject or "").strip() or _default_subject(cotizacion.id, cotizacion.nombre_cotizacion)
    body = (payload.body or "").strip() or _default_body(current.nombre, current.cargo, cotizacion.nombre_cotizacion)

    gmail_message_id = send_email_with_pdf(
        sender_email=sender_email,
        sender_name=current.nombre,
        to_email=to_email,
        subject=subject,
        body=body,
        pdf_filename=pdf_filename,
        pdf_bytes=pdf_bytes,
    )

    return CotizacionEmailOut(
        message="Correo enviado correctamente",
        sender_email=sender_email,
        to_email=to_email,
        gmail_message_id=gmail_message_id,
    )
