from fastapi import APIRouter

from app.api.v1.endpoints.cliente import router as cliente_router
from app.api.v1.endpoints.empleado import router as empleado_router
from app.api.v1.endpoints.oportunidad import router as oportunidad_router
from app.api.v1.endpoints.cotizacion import router as cotizacion_router
from app.api.v1.endpoints.proyecto import router as proyecto_router
from app.api.v1.endpoints.producto import router as producto_router
from app.api.v1.endpoints.despacho import router as despacho_router
from app.api.v1.endpoints.relaciones_proyecto import router as relaciones_router



api_router = APIRouter()
api_router.include_router(cliente_router, prefix="/clientes", tags=["clientes"])
api_router.include_router(empleado_router, prefix="/empleados", tags=["empleados"])
api_router.include_router(oportunidad_router, prefix="/oportunidades", tags=["oportunidades"])
api_router.include_router(cotizacion_router, prefix="/cotizaciones", tags=["cotizaciones"])
api_router.include_router(proyecto_router, prefix="/proyectos", tags=["proyectos"])
api_router.include_router(producto_router, prefix="/productos", tags=["productos"])
api_router.include_router(despacho_router, prefix="/despachos", tags=["despachos"])
api_router.include_router(relaciones_router, prefix="/proyectos", tags=["relaciones-proyecto"])
