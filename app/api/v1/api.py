# app/api/v1/api.py

from fastapi import APIRouter

from app.api.v1.endpoints import producto
from app.api.v1.endpoints import cliente
from app.api.v1.endpoints import oportunidad
from app.api.v1.endpoints import cotizacion
from app.api.v1.endpoints import fx
from app.api.v1.endpoints import pais

api_router = APIRouter()

api_router.include_router(producto.router, prefix="/productos", tags=["productos"])
api_router.include_router(cliente.router, prefix="/clientes", tags=["clientes"])
api_router.include_router(oportunidad.router, prefix="/oportunidades", tags=["oportunidades"])
api_router.include_router(cotizacion.router, prefix="/cotizaciones", tags=["cotizaciones"])

api_router.include_router(fx.router, prefix="/fx", tags=["fx"])
api_router.include_router(pais.router, prefix="/paises", tags=["paises"])
