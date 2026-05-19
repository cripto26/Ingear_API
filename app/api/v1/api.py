from fastapi import APIRouter

from app.api.v1.endpoints import apu
from app.api.v1.endpoints import auth
from app.api.v1.endpoints import cliente
from app.api.v1.endpoints import contacto
from app.api.v1.endpoints import cuenta_cobro
from app.api.v1.endpoints import cotizacion
from app.api.v1.endpoints import despacho
from app.api.v1.endpoints import empleado
from app.api.v1.endpoints import fx
from app.api.v1.endpoints import notificacion
from app.api.v1.endpoints import oportunidad
from app.api.v1.endpoints import pais
from app.api.v1.endpoints import producto
from app.api.v1.endpoints import proyecto
from app.api.v1.endpoints import relaciones_proyecto

api_router = APIRouter()

api_router.include_router(apu.router, prefix="/apu", tags=["apu"])
api_router.include_router(producto.router, prefix="/productos", tags=["productos"])
api_router.include_router(cliente.router, prefix="/clientes", tags=["clientes"])
api_router.include_router(contacto.router, prefix="/contactos", tags=["contactos"])
api_router.include_router(oportunidad.router, prefix="/oportunidades", tags=["oportunidades"])
api_router.include_router(cotizacion.router, prefix="/cotizaciones", tags=["cotizaciones"])
api_router.include_router(cuenta_cobro.router, prefix="/cuentas-cobro", tags=["cuentas-cobro"])
api_router.include_router(proyecto.router, prefix="/proyectos", tags=["proyectos"])
api_router.include_router(despacho.router, prefix="/despachos", tags=["despachos"])
api_router.include_router(relaciones_proyecto.router, prefix="/proyectos", tags=["proyectos-relaciones"])
api_router.include_router(empleado.router, prefix="/empleados", tags=["empleados"])
api_router.include_router(fx.router, prefix="/fx", tags=["fx"])
api_router.include_router(pais.router, prefix="/paises", tags=["paises"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    notificacion.router,
    prefix="/notificaciones",
    tags=["notificaciones"],
)
