from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models.auth_refresh_session import AuthRefreshSession
from app.models.notificacion import Notificacion


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


def ensure_notificacion_table(engine: Engine) -> None:
    Notificacion.__table__.create(bind=engine, checkfirst=True)


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
