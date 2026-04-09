from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.api import api_router
from app.db.schema_updates import ensure_empleado_permisos_vistas_column
from app.db.session import engine

app = FastAPI(title=settings.APP_NAME)

# CORS para desarrollo local (Vite suele correr en 5173)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

# Permite abrir el frontend desde la misma red local durante desarrollo.
local_network_origin_regex = (
    r"^https?://"
    r"(localhost|127\.0\.0\.1|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"
    r"(:\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=local_network_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def ensure_schema_updates():
    ensure_empleado_permisos_vistas_column(engine)


@app.get("/")
def root():
    return {"ok": True, "name": settings.APP_NAME}
