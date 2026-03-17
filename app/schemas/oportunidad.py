from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class OportunidadBase(BaseModel):
    nombre_proyecto: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    marca_predominante: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[str] = None
    fecha_cierre: Optional[date] = None
    segmento: Optional[str] = None
    cotizaciones: Optional[str] = None
    observaciones: Optional[str] = None
    numero_empleado: Optional[int] = None
    nuevo_existente: Optional[str] = None


class OportunidadCreate(OportunidadBase):
    cliente_id: int
    responsable_cotizacion: int
    fecha_oportunidad: date


class OportunidadUpdate(BaseModel):
    cliente_id: Optional[int] = None
    responsable_cotizacion: Optional[int] = None
    fecha_oportunidad: Optional[date] = None
    nombre_proyecto: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    marca_predominante: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[str] = None
    fecha_cierre: Optional[date] = None
    segmento: Optional[str] = None
    cotizaciones: Optional[str] = None
    observaciones: Optional[str] = None
    numero_empleado: Optional[int] = None
    nuevo_existente: Optional[str] = None


class OportunidadOut(OportunidadBase):
    id: int
    cliente_id: Optional[int] = None
    responsable_cotizacion: Optional[int] = None
    fecha_oportunidad: Optional[date] = None

    class Config:
        from_attributes = True
