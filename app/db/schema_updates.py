from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models.apu import Apu
from app.models.auth_refresh_session import AuthRefreshSession
from app.models.cuenta_cobro import CuentaCobro
from app.models.notificacion import Notificacion
from app.db.text_normalization import BUSINESS_TEXT_COLUMNS


def ensure_empleado_permisos_vistas_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("empleado"):
        return

    columns = {column["name"] for column in inspector.get_columns("empleado")}
    if "permisos_vistas" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE empleado ADD COLUMN permisos_vistas TEXT")
        )


def ensure_empleado_jefe_id_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("empleado"):
        return

    columns = {column["name"] for column in inspector.get_columns("empleado")}
    if "jefe_id" in columns:
        return

    with engine.begin() as connection:
        if "jede_id" in columns:
            connection.execute(
                text("ALTER TABLE empleado RENAME COLUMN jede_id TO jefe_id")
            )
            return

        connection.execute(text("ALTER TABLE empleado ADD COLUMN jefe_id INTEGER"))


def ensure_auth_refresh_session_table(engine: Engine) -> None:
    AuthRefreshSession.__table__.create(bind=engine, checkfirst=True)


def ensure_apu_table(engine: Engine) -> None:
    Apu.__table__.create(bind=engine, checkfirst=True)


def ensure_apu_tipo_producto_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("apu"):
        return

    columns = {column["name"] for column in inspector.get_columns("apu")}
    if "tipo_producto" in columns:
        return

    if "subtipo" not in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE apu RENAME COLUMN subtipo TO tipo_producto")
        )


def ensure_apu_categoria_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("apu"):
        return

    columns = {column["name"] for column in inspector.get_columns("apu")}
    if "categoria" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE apu ADD COLUMN categoria VARCHAR(120)"))


def ensure_notificacion_table(engine: Engine) -> None:
    Notificacion.__table__.create(bind=engine, checkfirst=True)


def ensure_cuenta_cobro_table(engine: Engine) -> None:
    CuentaCobro.__table__.create(bind=engine, checkfirst=True)


def ensure_producto_precio_inventario_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("producto"):
        return

    columns = {column["name"] for column in inspector.get_columns("producto")}
    if "precio_inventario" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE producto ADD COLUMN precio_inventario NUMERIC(14, 2)")
        )


def ensure_producto_categoria_tipo_producto_columns(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("producto"):
        return

    columns = {column["name"] for column in inspector.get_columns("producto")}
    has_old_categoria = "categoria" in columns and "subtipo" in columns

    with engine.begin() as connection:
        if has_old_categoria:
            connection.execute(text("ALTER TABLE producto DROP COLUMN categoria"))
            columns.remove("categoria")

        if "tipo_producto" in columns and "categoria" not in columns:
            connection.execute(
                text("ALTER TABLE producto RENAME COLUMN tipo_producto TO categoria")
            )
            columns.remove("tipo_producto")
            columns.add("categoria")

        if "subtipo" in columns:
            if "tipo_producto" in columns:
                connection.execute(text("ALTER TABLE producto DROP COLUMN subtipo"))
            else:
                connection.execute(
                    text("ALTER TABLE producto RENAME COLUMN subtipo TO tipo_producto")
                )
                columns.add("tipo_producto")
            columns.remove("subtipo")

        if "categoria" not in columns:
            connection.execute(
                text("ALTER TABLE producto ADD COLUMN categoria VARCHAR(120)")
            )

        if "tipo_producto" not in columns:
            connection.execute(
                text("ALTER TABLE producto ADD COLUMN tipo_producto VARCHAR(120)")
            )


def normalize_producto_pais_origen_shenzhen(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("producto"):
        return

    columns = {column["name"] for column in inspector.get_columns("producto")}
    if not {"ciudad", "pais_origen"}.issubset(columns):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE producto "
                "SET pais_origen = 'CHINA' "
                "WHERE UPPER(TRIM(ciudad)) = 'SHENZHEN' "
                "AND COALESCE(pais_origen, '') <> 'CHINA'"
            )
        )


def normalize_producto_codes_uppercase(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("producto"):
        return

    columns = {column["name"] for column in inspector.get_columns("producto")}
    if not {"id", "codigo_producto"}.issubset(columns):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE producto AS current_product "
                "SET codigo_producto = UPPER(current_product.codigo_producto) "
                "WHERE current_product.codigo_producto IS NOT NULL "
                "AND current_product.codigo_producto "
                "<> UPPER(current_product.codigo_producto) "
                "AND NOT EXISTS ("
                "SELECT 1 FROM producto AS other_product "
                "WHERE other_product.id <> current_product.id "
                "AND UPPER(other_product.codigo_producto) "
                "= UPPER(current_product.codigo_producto)"
                ")"
            )
        )


def normalize_business_text_uppercase(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    preparer = engine.dialect.identifier_preparer

    with engine.begin() as connection:
        for table_name, configured_columns in BUSINESS_TEXT_COLUMNS.items():
            if table_name not in table_names:
                continue

            columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            quoted_table = preparer.quote(table_name)

            for column_name in configured_columns:
                if column_name not in columns:
                    continue

                quoted_column = preparer.quote(column_name)
                connection.execute(
                    text(
                        f"UPDATE {quoted_table} "
                        f"SET {quoted_column} = UPPER({quoted_column}) "
                        f"WHERE {quoted_column} IS NOT NULL "
                        f"AND {quoted_column} <> UPPER({quoted_column})"
                    )
                )


def ensure_cotizacion_version_estado_column(engine: Engine) -> None:
    inspector = inspect(engine)

    if not inspector.has_table("cotizacion_versiones_v2"):
        return

    columns = {
        column["name"] for column in inspector.get_columns("cotizacion_versiones_v2")
    }
    if "estado" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE cotizacion_versiones_v2 "
                "ADD COLUMN estado VARCHAR(50)"
            )
        )


def ensure_cotizacion_trm_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = ("cotizacion", "cotizacion_versiones_v2")
    missing_tables = [
        table_name for table_name in table_names if not inspector.has_table(table_name)
    ]
    if missing_tables:
        return

    columns_by_table = {
        table_name: {
            column["name"] for column in inspector.get_columns(table_name)
        }
        for table_name in table_names
    }

    with engine.begin() as connection:
        for table_name in table_names:
            if "trm" in columns_by_table[table_name]:
                continue

            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN trm NUMERIC(14, 4)")
            )
