from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class CotizacionBase(BaseModel):
    consecutivo: str
    id_cotizador: int
    url_cotizacion: Optional[str] = None
    valor: Optional[Decimal] = None
    tiempo_entrega: Optional[str] = None
    nombre_cotizacion: Optional[str] = None
    tipo_cotizacion: Optional[str] = None
    etapa_cotizacion: Optional[str] = None
    forma_pago: Optional[str] = None
    total: Optional[Decimal] = None


class CotizacionCreate(CotizacionBase):
    pass


class CotizacionUpdate(BaseModel):
    consecutivo: Optional[str] = None
    id_cotizador: Optional[int] = None
    url_cotizacion: Optional[str] = None
    valor: Optional[Decimal] = None
    tiempo_entrega: Optional[str] = None
    nombre_cotizacion: Optional[str] = None
    tipo_cotizacion: Optional[str] = None
    etapa_cotizacion: Optional[str] = None
    forma_pago: Optional[str] = None
    total: Optional[Decimal] = None


class CotizacionOut(CotizacionBase):
    id: int
    fecha_creacion: datetime

    class Config:
        from_attributes = True
