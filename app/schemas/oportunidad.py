from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class OportunidadBase(BaseModel):
    cliente_id: int
    nombre_proyecto: Optional[str] = None
    tipologia: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    responsable_cotizacion: Optional[int] = None
    marca_predominante: Optional[str] = None
    fecha_oportunidad: Optional[date] = None
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[Decimal] = None
    fecha_cierre: Optional[date] = None


class OportunidadCreate(OportunidadBase):
    pass


class OportunidadUpdate(BaseModel):
    cliente_id: Optional[int] = None
    nombre_proyecto: Optional[str] = None
    tipologia: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    responsable_cotizacion:int
    marca_predominante: Optional[str] = None
    fecha_oportunidad: date
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[Decimal] = None
    fecha_cierre: Optional[date] = None


class OportunidadOut(OportunidadBase):
    id: int

    class Config:
        from_attributes = True
