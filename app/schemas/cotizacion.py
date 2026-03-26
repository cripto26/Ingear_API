import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def _parse_productos(value: Any) -> Any:
    if value is None:
        return None
    if value == "":
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("El campo productos debe contener un JSON valido.") from exc
    return value


class CotizacionProductoItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id_producto: int = Field(
        gt=0,
        validation_alias=AliasChoices("id_producto", "producto_id"),
    )
    cantidad: int = Field(gt=0)


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
    productos: list[CotizacionProductoItem] = Field(default_factory=list)

    @field_validator("productos", mode="before")
    @classmethod
    def parse_productos(cls, value: Any) -> Any:
        parsed = _parse_productos(value)
        return [] if parsed is None else parsed


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
    productos: Optional[list[CotizacionProductoItem]] = None

    @field_validator("productos", mode="before")
    @classmethod
    def parse_productos(cls, value: Any) -> Any:
        return _parse_productos(value)


class CotizacionOut(CotizacionBase):
    id: int
    fecha_creacion: datetime

    class Config:
        from_attributes = True
