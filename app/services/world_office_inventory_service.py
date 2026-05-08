from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock
from time import monotonic
from typing import Iterable, Sequence

from app.core.config import settings
from app.models.producto import Producto

logger = logging.getLogger(__name__)
_inventory_cache_lock = Lock()
_inventory_cache_expires_at = 0.0
_inventory_cache: dict[str, int] | None = None


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
    database: str | None
    bodega_codigo: str | None


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


def _normalize_inventory_quantity(value: object) -> int:
    try:
        decimal_value = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return 0

    return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _product_lookup_values(producto: Producto) -> list[str]:
    values: list[str] = []
    for raw in (producto.codigo_producto, producto.referencia):
        value = str(raw or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _find_inventory_for_product(
    producto: Producto,
    inventory_by_code: dict[str, int],
) -> int | None:
    for value in _product_lookup_values(producto):
        quantity = inventory_by_code.get(_normalize_lookup(value))
        if quantity is not None:
            return quantity

    return None


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


def _load_world_office_inventory_snapshot() -> dict[str, int]:
    inventory_by_code: dict[str, int] = {}
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
                LTRIM(RTRIM(CodigoInventario)) AS codigo,
                SUM(COALESCE(Existencia, 0)) AS existencia
            FROM Vista_ExistenciasPorBodegas
            WHERE CodigoInventario IS NOT NULL
              {bodega_filter}
            GROUP BY LTRIM(RTRIM(CodigoInventario))
            """,
            params,
        )

        for codigo, existencia in cursor.fetchall():
            key = _normalize_lookup(codigo)
            if not key:
                continue
            inventory_by_code[key] = _normalize_inventory_quantity(existencia)
    except WorldOfficeInventoryError:
        raise
    except Exception as exc:
        raise WorldOfficeInventoryError(
            "No se pudo consultar existencias en World Office."
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return inventory_by_code


def fetch_world_office_inventory_snapshot(
    *,
    force_refresh: bool = False,
) -> dict[str, int]:
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
) -> dict[str, int]:
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
        quantity = _find_inventory_for_product(producto, inventory_by_code)
        if quantity is not None:
            producto.cantidad_inventario = quantity


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

    for producto in productos:
        quantity = _find_inventory_for_product(producto, inventory_by_code)
        if quantity is None:
            continue

        matched += 1
        if int(producto.cantidad_inventario or 0) != quantity:
            producto.cantidad_inventario = quantity
            updated += 1

    total = len(productos)
    return WorldOfficeInventorySyncStats(
        total_productos=total,
        matched_productos=matched,
        unmatched_productos=total - matched,
        updated_productos=updated,
        database=settings.WORLD_OFFICE_DATABASE,
        bodega_codigo=settings.WORLD_OFFICE_BODEGA_CODIGO,
    )
