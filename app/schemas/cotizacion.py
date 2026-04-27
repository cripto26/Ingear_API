import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator




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
    particion: int = Field(default=1, ge=1)
    costo_fabrica_override: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices(
            "costo_fabrica_override",
            "costoFabricaOverride",
        ),
    )


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
    tipo_servicio: Optional[str] = None
    sub_total: Optional[Decimal] = None
    total: Optional[Decimal] = None
    estado: Optional[str] = None
    productos: list[CotizacionProductoItem] = Field(default_factory=list)

    @field_validator("productos", mode="before")
    @classmethod
    def parse_productos(cls, value: Any) -> Any:
        parsed = _parse_productos(value)
        return [] if parsed is None else parsed


class CotizacionCreate(CotizacionBase):
    fecha_probable_venta: Optional[date] = None
    estado: Optional[str] = "1"


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
    tipo_servicio: Optional[str] = None
    fecha_probable_venta: Optional[date] = None
    sub_total: Optional[Decimal] = None
    total: Optional[Decimal] = None
    estado: Optional[str] = None
    productos: Optional[list[CotizacionProductoItem]] = None
    crear_proyecto_ganada: Optional[bool] = None

    @field_validator("productos", mode="before")
    @classmethod
    def parse_productos(cls, value: Any) -> Any:
        return _parse_productos(value)


class CotizacionOut(CotizacionBase):
    id: int
    fecha_creacion: datetime
    proyecto_creado_id: Optional[int] = None

    class Config:
        from_attributes = True


class CotizacionEmailIn(BaseModel):
    to_email: Optional[EmailStr] = None
    subject: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = None
    pdf_base64: str = Field(min_length=20)
    pdf_filename: str = Field(default="cotizacion.pdf", min_length=1, max_length=255)


class CotizacionEmailOut(BaseModel):
    message: str
    sender_email: EmailStr
    to_email: EmailStr
    gmail_message_id: str
