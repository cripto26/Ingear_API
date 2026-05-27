from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock
from time import monotonic
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.producto import Producto

logger = logging.getLogger(__name__)
_inventory_cache_lock = Lock()
_inventory_cache_expires_at = 0.0
_inventory_cache: dict[str, "WorldOfficeInventoryRecord"] | None = None

WORLD_OFFICE_INVENTORY_PRICE_VIEW = "Vista_Tabla_Inventarios"
WORLD_OFFICE_INVENTORY_PRICE_COLUMN = "Precio1"
WORLD_OFFICE_PRODUCT_CODE_EXPR = """
COALESCE(
    NULLIF(LTRIM(RTRIM(CAST(CodigoInventario AS NVARCHAR(255)))), ''),
    NULLIF(LTRIM(RTRIM(CAST([CódigoInventario] AS NVARCHAR(255)))), ''),
    NULLIF(LTRIM(RTRIM(CAST(Codigo_Producto AS NVARCHAR(255)))), '')
)
"""
WORLD_OFFICE_STOCK_CODE_EXPR = """
COALESCE(
    NULLIF(LTRIM(RTRIM(CAST(CodigoInventario AS NVARCHAR(255)))), ''),
    NULLIF(LTRIM(RTRIM(CAST([CódigoInventario] AS NVARCHAR(255)))), '')
)
"""
WORLD_OFFICE_DESCRIPTION_EXPR = """
COALESCE(
    NULLIF(LTRIM(RTRIM(CAST(Descripcion AS NVARCHAR(1000)))), ''),
    NULLIF(LTRIM(RTRIM(CAST([Descripción] AS NVARCHAR(1000)))), '')
)
"""


class WorldOfficeInventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorldOfficeInventoryStatus:
    enabled: bool
    configured: bool
    connected: bool
    database: str | None = None
    bodega_codigo: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class WorldOfficeInventorySyncStats:
    total_productos: int
    matched_productos: int
    unmatched_productos: int
    updated_productos: int
    updated_cantidades: int
    updated_precios: int
    database: str | None
    bodega_codigo: str | None


@dataclass(frozen=True)
class WorldOfficeProductImportStats:
    productos_worldoffice: int
    productos_existentes: int
    productos_importados: int
    database: str | None
    bodega_codigo: str | None


@dataclass(frozen=True)
class WorldOfficeInventoryRecord:
    cantidad_inventario: int | None = None
    precio_inventario: Decimal | None = None


@dataclass
class WorldOfficeProductRecord:
    codigo: str
    descripcion: str | None = None
    categoria: str | None = None
    tipo_producto: str | None = None
    subtipo: str | None = None
    precio_inventario: Decimal | None = None
    arancel: Decimal | None = None
    cantidad_inventario: int = 0


def is_world_office_inventory_enabled() -> bool:
    return settings.WORLD_OFFICE_ENABLED and _has_required_settings()


def _has_required_settings() -> bool:
    return bool(
        settings.WORLD_OFFICE_SERVER
        and settings.WORLD_OFFICE_DATABASE
        and settings.WORLD_OFFICE_USERNAME
        and settings.WORLD_OFFICE_PASSWORD
    )


def _get_pyodbc():
    try:
        import pyodbc
    except ImportError as exc:
        raise WorldOfficeInventoryError(
            "pyodbc no esta instalado en el entorno del backend."
        ) from exc

    return pyodbc


def _connection_string() -> str:
    driver = str(settings.WORLD_OFFICE_ODBC_DRIVER or "SQL Server").strip()
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={settings.WORLD_OFFICE_SERVER};"
        f"DATABASE={settings.WORLD_OFFICE_DATABASE};"
        f"UID={settings.WORLD_OFFICE_USERNAME};"
        f"PWD={settings.WORLD_OFFICE_PASSWORD};"
        "TrustServerCertificate=yes;"
        f"Connection Timeout={settings.WORLD_OFFICE_CONNECTION_TIMEOUT_SECONDS};"
    )


def _connect():
    pyodbc = _get_pyodbc()
    try:
        connection = pyodbc.connect(_connection_string())
    except pyodbc.Error as exc:
        raise WorldOfficeInventoryError(
            "No se pudo conectar con World Office."
        ) from exc

    connection.timeout = settings.WORLD_OFFICE_QUERY_TIMEOUT_SECONDS
    return connection


def _normalize_lookup(value: object) -> str:
    return str(value or "").strip().casefold()


def _clean_text(value: object, max_length: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None

    if max_length is None:
        return text

    return text[:max_length]


def _normalize_inventory_quantity(value: object) -> int:
    try:
        decimal_value = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return 0

    return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalize_inventory_price(value: object) -> Decimal | None:
    if value is None:
        return None

    clean = str(value).strip()
    if not clean:
        return None

    try:
        decimal_value = Decimal(clean)
    except (InvalidOperation, ValueError):
        return None

    if decimal_value <= 0:
        return None

    return decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _same_inventory_price(current: object, incoming: Decimal) -> bool:
    current_value = _normalize_inventory_price(current)
    return current_value == incoming


def _product_lookup_values(producto: Producto) -> list[str]:
    values: list[str] = []
    for raw in (producto.codigo_producto, producto.referencia):
        value = str(raw or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _with_inventory_quantity(
    record: WorldOfficeInventoryRecord | None,
    quantity: int,
) -> WorldOfficeInventoryRecord:
    return WorldOfficeInventoryRecord(
        cantidad_inventario=quantity,
        precio_inventario=record.precio_inventario if record else None,
    )


def _with_inventory_price(
    record: WorldOfficeInventoryRecord | None,
    price: Decimal,
    *,
    replace: bool = False,
) -> WorldOfficeInventoryRecord:
    current_price = record.precio_inventario if record else None
    next_price = (
        price
        if replace or current_price is None or price > current_price
        else current_price
    )
    return WorldOfficeInventoryRecord(
        cantidad_inventario=record.cantidad_inventario if record else None,
        precio_inventario=next_price,
    )


def _load_world_office_inventory_costs(
    cursor,
    *,
    bodega_codigo: str = "",
) -> list[tuple[object, object]]:
    params: list[object] = []
    bodega_filter = ""

    if bodega_codigo:
        bodega_filter = " AND LTRIM(RTRIM(e.Codigo_Bodega)) = ?"
        params.append(bodega_codigo)

    stock_code_expr = (
        "NULLIF(LTRIM(RTRIM(CAST(e.CodigoInventario AS NVARCHAR(255)))), '')"
    )

    cursor.execute(
        f"""
        WITH latest_cost AS (
            SELECT
                {stock_code_expr} AS codigo,
                COALESCE(
                    NULLIF(m.CostoPromedio, 0),
                    NULLIF(m.Costo_Promedio, 0),
                    NULLIF(m.Valor_Unitario, 0)
                ) AS precio,
                ROW_NUMBER() OVER (
                    PARTITION BY {stock_code_expr}
                    ORDER BY m.Autonumerico DESC
                ) AS rn
            FROM Vista_ExistenciasPorBodegas e
            INNER JOIN Vista_Tabla_Movimientos_Inventario m
                ON m.IdInventario = e.IdInventario
            WHERE {stock_code_expr} IS NOT NULL
              AND COALESCE(e.Existencia, 0) > 0
              AND COALESCE(
                    NULLIF(m.CostoPromedio, 0),
                    NULLIF(m.Costo_Promedio, 0),
                    NULLIF(m.Valor_Unitario, 0)
                  ) IS NOT NULL
              {bodega_filter}
        )
        SELECT codigo, precio
        FROM latest_cost
        WHERE rn = 1
        """,
        params,
    )

    return list(cursor.fetchall())


def _find_inventory_record_for_product(
    producto: Producto,
    inventory_by_code: dict[str, WorldOfficeInventoryRecord],
) -> WorldOfficeInventoryRecord | None:
    for value in _product_lookup_values(producto):
        record = inventory_by_code.get(_normalize_lookup(value))
        if record is not None:
            return record

    return None


def _merge_world_office_product_record(
    products_by_code: dict[str, WorldOfficeProductRecord],
    codigo: object,
    descripcion: object,
    precio: object,
    categoria: object,
    tipo_producto: object = None,
    subtipo: object = None,
    arancel: object = None,
) -> None:
    key = _normalize_lookup(codigo)
    clean_code = _clean_text(codigo, 300)
    if not key or clean_code is None:
        return

    incoming_price = _normalize_inventory_price(precio)
    incoming_arancel = _normalize_inventory_price(arancel)
    record = products_by_code.get(key)
    if record is None:
        products_by_code[key] = WorldOfficeProductRecord(
            codigo=clean_code,
            descripcion=_clean_text(descripcion, 1000),
            categoria=_clean_text(categoria, 120),
            tipo_producto=_clean_text(tipo_producto, 120),
            subtipo=_clean_text(subtipo, 120),
            precio_inventario=incoming_price,
            arancel=incoming_arancel,
        )
        return

    if record.descripcion is None:
        record.descripcion = _clean_text(descripcion, 1000)

    if record.categoria is None:
        record.categoria = _clean_text(categoria, 120)

    if record.tipo_producto is None:
        record.tipo_producto = _clean_text(tipo_producto, 120)

    if record.subtipo is None:
        record.subtipo = _clean_text(subtipo, 120)

    if (
        incoming_price is not None
        and (
            record.precio_inventario is None
            or incoming_price > record.precio_inventario
        )
    ):
        record.precio_inventario = incoming_price

    if incoming_arancel is not None and record.arancel is None:
        record.arancel = incoming_arancel


def get_world_office_inventory_status() -> WorldOfficeInventoryStatus:
    configured = _has_required_settings()
    if not settings.WORLD_OFFICE_ENABLED:
        return WorldOfficeInventoryStatus(
            enabled=False,
            configured=configured,
            connected=False,
            database=settings.WORLD_OFFICE_DATABASE,
            bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
        )

    if not configured:
        return WorldOfficeInventoryStatus(
            enabled=True,
            configured=False,
            connected=False,
            database=settings.WORLD_OFFICE_DATABASE,
            bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
            error="Faltan variables WORLD_OFFICE_* en el .env.",
        )

    connection = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        cursor.execute("SELECT TOP 1 1 FROM Vista_ExistenciasPorBodegas")
        cursor.fetchone()
        cursor.execute(f"SELECT TOP 1 1 FROM {WORLD_OFFICE_INVENTORY_PRICE_VIEW}")
        cursor.fetchone()
    except WorldOfficeInventoryError as exc:
        return WorldOfficeInventoryStatus(
            enabled=True,
            configured=True,
            connected=False,
            database=settings.WORLD_OFFICE_DATABASE,
            bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
            error=str(exc),
        )
    except Exception as exc:
        return WorldOfficeInventoryStatus(
            enabled=True,
            configured=True,
            connected=False,
            database=settings.WORLD_OFFICE_DATABASE,
            bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
            error=str(exc),
        )
    finally:
        if connection is not None:
            connection.close()

    return WorldOfficeInventoryStatus(
        enabled=True,
        configured=True,
        connected=True,
        database=settings.WORLD_OFFICE_DATABASE,
        bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
    )


def _load_world_office_inventory_snapshot() -> dict[str, WorldOfficeInventoryRecord]:
    inventory_by_code: dict[str, WorldOfficeInventoryRecord] = {}
    bodega_codigo = str(settings.WORLD_OFFICE_BODEGA_CODIGO or "").strip()

    connection = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        params: list[object] = []
        bodega_filter = ""

        if bodega_codigo:
            bodega_filter = " AND LTRIM(RTRIM(Codigo_Bodega)) = ?"
            params.append(bodega_codigo)

        cursor.execute(
            f"""
            SELECT
                {WORLD_OFFICE_STOCK_CODE_EXPR} AS codigo,
                SUM(COALESCE(Existencia, 0)) AS existencia
            FROM Vista_ExistenciasPorBodegas
            WHERE {WORLD_OFFICE_STOCK_CODE_EXPR} IS NOT NULL
              {bodega_filter}
            GROUP BY {WORLD_OFFICE_STOCK_CODE_EXPR}
            """,
            params,
        )

        for codigo, existencia in cursor.fetchall():
            key = _normalize_lookup(codigo)
            if not key:
                continue
            inventory_by_code[key] = _with_inventory_quantity(
                inventory_by_code.get(key),
                _normalize_inventory_quantity(existencia),
            )

        cursor.execute(
            f"""
            SELECT
                {WORLD_OFFICE_PRODUCT_CODE_EXPR} AS codigo,
                MAX(COALESCE({WORLD_OFFICE_INVENTORY_PRICE_COLUMN}, 0)) AS precio
            FROM {WORLD_OFFICE_INVENTORY_PRICE_VIEW}
            WHERE {WORLD_OFFICE_PRODUCT_CODE_EXPR} IS NOT NULL
            GROUP BY {WORLD_OFFICE_PRODUCT_CODE_EXPR}
            """
        )

        for codigo, precio in cursor.fetchall():
            key = _normalize_lookup(codigo)
            price = _normalize_inventory_price(precio)
            if not key or price is None:
                continue
            inventory_by_code[key] = _with_inventory_price(
                inventory_by_code.get(key),
                price,
            )

        for codigo, precio in _load_world_office_inventory_costs(
            cursor,
            bodega_codigo=bodega_codigo,
        ):
            key = _normalize_lookup(codigo)
            price = _normalize_inventory_price(precio)
            if not key or price is None:
                continue
            inventory_by_code[key] = _with_inventory_price(
                inventory_by_code.get(key),
                price,
                replace=True,
            )
    except WorldOfficeInventoryError:
        raise
    except Exception as exc:
        raise WorldOfficeInventoryError(
            "No se pudo consultar existencias y precios de inventario en World Office."
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return inventory_by_code


def _load_world_office_product_catalog() -> dict[str, WorldOfficeProductRecord]:
    products_by_code: dict[str, WorldOfficeProductRecord] = {}
    bodega_codigo = str(settings.WORLD_OFFICE_BODEGA_CODIGO or "").strip()

    connection = None
    try:
        connection = _connect()
        cursor = connection.cursor()

        cursor.execute(
            f"""
            SELECT
                {WORLD_OFFICE_PRODUCT_CODE_EXPR} AS codigo,
                MAX(CAST(COALESCE({WORLD_OFFICE_DESCRIPTION_EXPR}, '') AS NVARCHAR(1000))) AS descripcion,
                CAST(MAX(COALESCE({WORLD_OFFICE_INVENTORY_PRICE_COLUMN}, 0)) AS DECIMAL(14, 2)) AS precio,
                MAX(CAST(COALESCE(
                    NULLIF(LTRIM(RTRIM(CAST(Descripcion_Grupo_Dos AS NVARCHAR(120)))), ''),
                    NULLIF(LTRIM(RTRIM(CAST(Descripcion_Grupo_Uno AS NVARCHAR(120)))), ''),
                    NULLIF(LTRIM(RTRIM(CAST(Clasificacion AS NVARCHAR(120)))), ''),
                    ''
                ) AS NVARCHAR(120))) AS categoria,
                MAX(CAST(COALESCE(Clasificacion, '') AS NVARCHAR(120))) AS tipo_producto,
                MAX(CAST(COALESCE(Descripcion_Grupo_Tres, '') AS NVARCHAR(120))) AS subtipo,
                CAST(MAX(COALESCE(porcArancel, 0)) AS DECIMAL(14, 2)) AS arancel
            FROM {WORLD_OFFICE_INVENTORY_PRICE_VIEW}
            WHERE {WORLD_OFFICE_PRODUCT_CODE_EXPR} IS NOT NULL
            GROUP BY {WORLD_OFFICE_PRODUCT_CODE_EXPR}
            """
        )

        for (
            codigo,
            descripcion,
            precio,
            categoria,
            tipo_producto,
            subtipo,
            arancel,
        ) in cursor.fetchall():
            _merge_world_office_product_record(
                products_by_code,
                codigo,
                descripcion,
                precio,
                categoria,
                tipo_producto,
                subtipo,
                arancel,
            )

        params: list[object] = []
        bodega_filter = ""
        if bodega_codigo:
            bodega_filter = " AND LTRIM(RTRIM(Codigo_Bodega)) = ?"
            params.append(bodega_codigo)

        cursor.execute(
            f"""
            SELECT
                {WORLD_OFFICE_STOCK_CODE_EXPR} AS codigo,
                SUM(COALESCE(Existencia, 0)) AS existencia
            FROM Vista_ExistenciasPorBodegas
            WHERE {WORLD_OFFICE_STOCK_CODE_EXPR} IS NOT NULL
              {bodega_filter}
            GROUP BY {WORLD_OFFICE_STOCK_CODE_EXPR}
            """,
            params,
        )

        for codigo, existencia in cursor.fetchall():
            key = _normalize_lookup(codigo)
            record = products_by_code.get(key)
            if record is not None:
                record.cantidad_inventario = _normalize_inventory_quantity(existencia)

        for codigo, precio in _load_world_office_inventory_costs(
            cursor,
            bodega_codigo=bodega_codigo,
        ):
            key = _normalize_lookup(codigo)
            record = products_by_code.get(key)
            price = _normalize_inventory_price(precio)

            if record is not None and price is not None:
                record.precio_inventario = price
    except WorldOfficeInventoryError:
        raise
    except Exception as exc:
        raise WorldOfficeInventoryError(
            "No se pudo consultar el catalogo de productos en World Office."
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return products_by_code


def fetch_world_office_inventory_snapshot(
    *,
    force_refresh: bool = False,
) -> dict[str, WorldOfficeInventoryRecord]:
    if not is_world_office_inventory_enabled():
        return {}

    global _inventory_cache, _inventory_cache_expires_at

    ttl_seconds = max(0, settings.WORLD_OFFICE_INVENTORY_CACHE_SECONDS)
    now = monotonic()

    with _inventory_cache_lock:
        if (
            not force_refresh
            and _inventory_cache is not None
            and now < _inventory_cache_expires_at
        ):
            return dict(_inventory_cache)

    inventory = _load_world_office_inventory_snapshot()

    with _inventory_cache_lock:
        _inventory_cache = dict(inventory)
        _inventory_cache_expires_at = now + ttl_seconds

    return inventory


def fetch_world_office_inventory_by_codes(
    codes: Iterable[object],
    *,
    force_refresh: bool = False,
) -> dict[str, WorldOfficeInventoryRecord]:
    if not is_world_office_inventory_enabled():
        return {}

    clean_codes = sorted(
        {
            _normalize_lookup(code)
            for code in codes
            if str(code or "").strip()
        }
    )
    if not clean_codes:
        return {}

    inventory = fetch_world_office_inventory_snapshot(force_refresh=force_refresh)
    return {code: inventory[code] for code in clean_codes if code in inventory}


def import_missing_world_office_products(
    db: Session,
) -> WorldOfficeProductImportStats:
    if not is_world_office_inventory_enabled():
        raise WorldOfficeInventoryError(
            "La integracion con World Office no esta habilitada o configurada."
        )

    products_by_code = _load_world_office_product_catalog()
    existing_codes: set[str] = set()

    rows = db.execute(
        select(Producto.codigo_producto, Producto.referencia)
    ).all()
    for codigo_producto, referencia in rows:
        for value in (codigo_producto, referencia):
            key = _normalize_lookup(value)
            if key:
                existing_codes.add(key)

    existing_count = 0
    imported_count = 0

    for key, record in products_by_code.items():
        clean_code = _clean_text(record.codigo, 300)
        if clean_code is None:
            continue

        clean_code_key = _normalize_lookup(clean_code)
        if key in existing_codes or clean_code_key in existing_codes:
            existing_count += 1
            continue

        db.add(
            Producto(
                codigo_producto=clean_code,
                referencia=_clean_text(record.codigo, 500),
                descripcion=_clean_text(record.descripcion, 1000),
                categoria=_clean_text(record.categoria, 120),
                tipo_producto=_clean_text(record.tipo_producto, 120),
                subtipo=_clean_text(record.subtipo, 120),
                precio_inventario=record.precio_inventario,
                arancel=record.arancel,
                cantidad_inventario=record.cantidad_inventario,
            )
        )
        existing_codes.add(key)
        existing_codes.add(clean_code_key)
        imported_count += 1

    if imported_count:
        db.flush()

    return WorldOfficeProductImportStats(
        productos_worldoffice=len(products_by_code),
        productos_existentes=existing_count,
        productos_importados=imported_count,
        database=settings.WORLD_OFFICE_DATABASE,
        bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
    )


def apply_world_office_inventory(productos: Sequence[Producto]) -> None:
    if not is_world_office_inventory_enabled() or not productos:
        return

    codes: list[str] = []
    for producto in productos:
        codes.extend(_product_lookup_values(producto))

    try:
        inventory_by_code = fetch_world_office_inventory_by_codes(codes)
    except WorldOfficeInventoryError:
        logger.exception("No se pudo enriquecer productos con World Office.")
        return

    if not inventory_by_code:
        return

    for producto in productos:
        record = _find_inventory_record_for_product(producto, inventory_by_code)
        if record is None:
            if int(producto.cantidad_inventario or 0) != 0:
                producto.cantidad_inventario = 0
            continue

        if record.cantidad_inventario is not None:
            producto.cantidad_inventario = record.cantidad_inventario

        if record.precio_inventario is not None:
            producto.precio_inventario = record.precio_inventario


def sync_world_office_inventory_to_products(
    productos: Sequence[Producto],
) -> WorldOfficeInventorySyncStats:
    if not is_world_office_inventory_enabled():
        raise WorldOfficeInventoryError(
            "La integracion con World Office no esta habilitada o configurada."
        )

    codes: list[str] = []
    for producto in productos:
        codes.extend(_product_lookup_values(producto))

    inventory_by_code = fetch_world_office_inventory_by_codes(
        codes,
        force_refresh=True,
    )
    matched = 0
    updated = 0
    updated_quantities = 0
    updated_prices = 0

    for producto in productos:
        record = _find_inventory_record_for_product(producto, inventory_by_code)
        if record is None:
            if int(producto.cantidad_inventario or 0) != 0:
                producto.cantidad_inventario = 0
                updated_quantities += 1
                updated += 1
            continue

        matched += 1
        changed = False

        if (
            record.cantidad_inventario is not None
            and int(producto.cantidad_inventario or 0) != record.cantidad_inventario
        ):
            producto.cantidad_inventario = record.cantidad_inventario
            updated_quantities += 1
            changed = True

        if (
            record.precio_inventario is not None
            and not _same_inventory_price(
                producto.precio_inventario,
                record.precio_inventario,
            )
        ):
            producto.precio_inventario = record.precio_inventario
            updated_prices += 1
            changed = True

        if changed:
            updated += 1

    total = len(productos)
    return WorldOfficeInventorySyncStats(
        total_productos=total,
        matched_productos=matched,
        unmatched_productos=total - matched,
        updated_productos=updated,
        updated_cantidades=updated_quantities,
        updated_precios=updated_prices,
        database=settings.WORLD_OFFICE_DATABASE,
        bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
    )
