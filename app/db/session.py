from importlib import import_module

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _resolve_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        return database_url

    try:
        import_module("psycopg")
        return database_url
    except ImportError:
        try:
            import_module("pg8000")
        except ImportError as pg8000_error:
            raise RuntimeError(
                "No se pudo cargar psycopg y pg8000 no esta instalado. "
                "Instala pg8000 o habilita psycopg en Windows App Control."
            ) from pg8000_error

        return url.set(drivername="postgresql+pg8000").render_as_string(
            hide_password=False
        )


engine = create_engine(_resolve_database_url(settings.DATABASE_URL), pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
 
