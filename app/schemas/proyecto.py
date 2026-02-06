from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class ProyectoBase(BaseModel):
    nombre: str
    url_cuenta_cobro: Optional[str] = None
    anticipo: Optional[Decimal] = None
    fecha_inicio: Optional[date] = None
    estado_logistica: Optional[str] = None
    estado_contable: Optional[str] = None
    estado_ingenieria: Optional[str] = None
    estado_factura: Optional[str] = None
    observacion: Optional[str] = None
    oportunidad_id: Optional[int] = None


class ProyectoCreate(ProyectoBase):
    pass


class ProyectoUpdate(BaseModel):
    nombre: Optional[str] = None
    url_cuenta_cobro: Optional[str] = None
    anticipo: Optional[Decimal] = None
    fecha_inicio: Optional[date] = None
    estado_logistica: Optional[str] = None
    estado_contable: Optional[str] = None
    estado_ingenieria: Optional[str] = None
    estado_factura: Optional[str] = None
    observacion: Optional[str] = None
    oportunidad_id: Optional[int] = None


class ProyectoOut(ProyectoBase):
    id: int

    class Config:
        from_attributes = True
