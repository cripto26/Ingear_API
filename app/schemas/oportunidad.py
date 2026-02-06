from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class OportunidadBase(BaseModel):
    # Required fields based on model (nullable=False)
    cliente_id: int
    responsable_cotizacion: int
    fecha_oportunidad: date

    # Optional fields (nullable=True)
    nombre_proyecto: Optional[str] = None
    tipologia: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    marca_predominante: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[Decimal] = None
    fecha_cierre: Optional[date] = None


class OportunidadCreate(OportunidadBase):
    pass


class OportunidadUpdate(BaseModel):
    # All fields are optional for updates
    cliente_id: Optional[int] = None
    responsable_cotizacion: Optional[int] = None
    fecha_oportunidad: Optional[date] = None
    nombre_proyecto: Optional[str] = None
    tipologia: Optional[str] = None
    tipo_contacto: Optional[str] = None
    ciudad: Optional[str] = None
    tipo_servicio: Optional[str] = None
    marca_predominante: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    rubro_sin_iva: Optional[Decimal] = None
    nivel_importancia: Optional[str] = None
    porcentaje_cierre: Optional[Decimal] = None
    fecha_cierre: Optional[date] = None


class OportunidadOut(OportunidadBase):
    id: int

    class Config:
        from_attributes = True
