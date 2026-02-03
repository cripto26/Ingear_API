from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class DespachoBase(BaseModel):
    fecha: Optional[date] = None
    transportadora: Optional[str] = None
    guia: Optional[str] = None
    valor_flete_seguro: Optional[Decimal] = None
    valor_mercancia: Optional[Decimal] = None
    ciudad_origen: Optional[str] = None
    contacto: Optional[str] = None
    estado: Optional[str] = None
    ciudad_destino: Optional[str] = None


class DespachoCreate(DespachoBase):
    pass


class DespachoUpdate(DespachoBase):
    pass


class DespachoOut(DespachoBase):
    id: int

    class Config:
        from_attributes = True
