from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class CotizacionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id_empleado: int = Field(validation_alias=AliasChoices("id_empleado", "id_cotizador"))
    id_oportunidad: int = Field(validation_alias=AliasChoices("id_oportunidad", "id_proyecto"))
    url_cotizacion: Optional[str] = None
    tiempo_entrega: Optional[str] = None
    nombre_cotizacion: Optional[str] = None
    tipo_cotizacion: Optional[str] = None
    etapa_cotizacion: Optional[str] = None
    forma_pago: Optional[str] = None
    sub_total: Optional[Decimal] = None
    total: Optional[Decimal] = None


class CotizacionCreate(CotizacionBase):
    pass


class CotizacionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id_empleado: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("id_empleado", "id_cotizador"),
    )
    id_oportunidad: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("id_oportunidad", "id_proyecto"),
    )
    url_cotizacion: Optional[str] = None
    tiempo_entrega: Optional[str] = None
    nombre_cotizacion: Optional[str] = None
    tipo_cotizacion: Optional[str] = None
    etapa_cotizacion: Optional[str] = None
    forma_pago: Optional[str] = None
    sub_total: Optional[Decimal] = None
    total: Optional[Decimal] = None


class CotizacionOut(CotizacionBase):
    id: int
    fecha_creacion: datetime

    class Config:
        from_attributes = True
