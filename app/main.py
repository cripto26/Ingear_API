from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.api import api_router
from app.db.schema_updates import (
    ensure_apu_categoria_column,
    ensure_apu_table,
    ensure_apu_tipo_producto_column,
    ensure_auth_refresh_session_table,
    ensure_cuenta_cobro_table,
    ensure_cotizacion_contacto_columns,
    ensure_cotizacion_logistica_tracking_tables,
    ensure_cotizacion_version_estado_column,
    ensure_cotizacion_trm_columns,
    ensure_cotizaciones_aprobada_table,
    ensure_empleado_jefe_id_column,
    ensure_empleado_permisos_vistas_column,
    ensure_notificacion_table,
    ensure_producto_categoria_tipo_producto_columns,
    ensure_producto_precio_inventario_column,
    remove_cotizacion_logistica_columns,
    normalize_business_text_uppercase,
    normalize_producto_codes_uppercase,
    normalize_producto_pais_origen_shenzhen,
)
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
    ensure_cotizacion_version_estado_column(engine)
    ensure_cotizacion_contacto_columns(engine)
    ensure_cotizacion_trm_columns(engine)
    ensure_cotizaciones_aprobada_table(engine)
    ensure_cotizacion_logistica_tracking_tables(engine)
    remove_cotizacion_logistica_columns(engine)
    ensure_empleado_jefe_id_column(engine)
    ensure_empleado_permisos_vistas_column(engine)
    ensure_auth_refresh_session_table(engine)
    ensure_apu_table(engine)
    ensure_apu_tipo_producto_column(engine)
    ensure_apu_categoria_column(engine)
    ensure_cuenta_cobro_table(engine)
    ensure_notificacion_table(engine)
    ensure_producto_precio_inventario_column(engine)
    ensure_producto_categoria_tipo_producto_columns(engine)
    normalize_producto_pais_origen_shenzhen(engine)
    normalize_producto_codes_uppercase(engine)
    normalize_business_text_uppercase(engine)


@app.get("/")
def root():
    return {"ok": True, "name": settings.APP_NAME}
