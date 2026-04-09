from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.models.auth_refresh_session import AuthRefreshSession


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


def ensure_auth_refresh_session_table(engine: Engine) -> None:
    AuthRefreshSession.__table__.create(bind=engine, checkfirst=True)
