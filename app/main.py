from fastapi import FastAPI

from app.core.config import settings
from app.db.session import engine
from app.db.base import Base



# Importa modelos para que SQLAlchemy los registre
import app.models  # noqa: F401

from app.api.v1.api import api_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    # Crea tablas (para desarrollo). En producción se recomienda Alembic.
    Base.metadata.create_all(bind=engine)

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
