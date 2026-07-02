import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator


LOGISTICA_STOCK_ESTADOS = {"incompleto", "parcial", "completo"}




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
    nombre_particion: str | None = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices(
            "nombre_particion",
            "nombreParticion",
            "partition_name",
        ),
    )
    tipo_importacion: str | None = Field(
        default=None,
        max_length=20,
        validation_alias=AliasChoices(
            "tipo_importacion",
            "tipoImportacion",
            "importType",
        ),
    )
    costo_fabrica_override: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices(
            "costo_fabrica_override",
            "costoFabricaOverride",
        ),
    )
    costo_instalacion: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices(
            "costo_instalacion",
            "costoInstalacion",
        ),
    )
    incluye_instalacion: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "incluye_instalacion",
            "incluyeInstalacion",
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
    contacto: Optional[str] = None
    tipo_servicio: Optional[str] = None
    trm: Optional[Decimal] = None
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
    contacto: Optional[str] = None
    tipo_servicio: Optional[str] = None
    fecha_probable_venta: Optional[date] = None
    trm: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None
    total: Optional[Decimal] = None
    estado: Optional[str] = None
    productos: Optional[list[CotizacionProductoItem]] = None
    crear_proyecto_ganada: Optional[bool] = None

    @field_validator("productos", mode="before")
    @classmethod
    def parse_productos(cls, value: Any) -> Any:
        return _parse_productos(value)


class CotizacionLogisticaUpdate(BaseModel):
    logistica_stock: Optional[int] = Field(default=None, ge=0)
    logistica_stock_estado: Optional[str] = None
    logistica_fecha_despacho: Optional[date] = None
    logistica_fecha_entrega: Optional[date] = None
    logistica_remision: Optional[str] = Field(default=None, max_length=120)
    logistica_unidades_pendientes: Optional[int] = Field(default=None, ge=0)
    logistica_orden_compra: Optional[str] = Field(default=None, max_length=120)
    logistica_observaciones: Optional[str] = None

    @field_validator("logistica_stock_estado")
    @classmethod
    def validate_logistica_stock_estado(cls, value: Optional[str]):
        if value is None:
            return None

        normalized = value.strip().lower()
        if normalized not in LOGISTICA_STOCK_ESTADOS:
            raise ValueError(
                "El estado de stock debe ser incompleto, parcial o completo."
            )

        return normalized


class CotizacionOut(CotizacionBase):
    id: int
    fecha_creacion: datetime
    empleado_nombre: Optional[str] = None
    proyecto_nombre: Optional[str] = None
    logistica_stock: Optional[int] = None
    logistica_stock_estado: Optional[str] = None
    logistica_fecha_despacho: Optional[date] = None
    logistica_fecha_entrega: Optional[date] = None
    logistica_remision: Optional[str] = None
    logistica_unidades_pendientes: Optional[int] = None
    logistica_orden_compra: Optional[str] = None
    logistica_observaciones: Optional[str] = None
    proyecto_creado_id: Optional[int] = None
    can_edit: bool = True
    can_duplicate: bool = True

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


class CotizacionLogisticaProductoOut(BaseModel):
    item_key: str
    id_producto: int
    codigo_producto: Optional[str] = None
    descripcion: Optional[str] = None
    marca: Optional[str] = None
    particion: int = 1
    nombre_particion: Optional[str] = None
    tipo_importacion: Optional[str] = None
    cantidad_cotizada: int = 0
    cantidad_inventario: int = 0
    cantidad_separada: int = 0
    cantidad_entregada: int = 0
    cantidad_pendiente: int = 0
    cantidad_por_entregar: int = 0
    porcentaje_entregado: float = 0
    observaciones_separacion: Optional[str] = None


class CotizacionLogisticaSeparacionItemIn(BaseModel):
    item_key: str = Field(min_length=1, max_length=180)
    cantidad_separada: int = Field(ge=0)
    observaciones: Optional[str] = None


class CotizacionLogisticaSeparacionIn(BaseModel):
    items: list[CotizacionLogisticaSeparacionItemIn] = Field(min_length=1)


class CotizacionLogisticaRemisionItemIn(BaseModel):
    item_key: str = Field(min_length=1, max_length=180)
    cantidad: int = Field(gt=0)


class CotizacionLogisticaRemisionCreate(BaseModel):
    numero_remision: Optional[str] = Field(default=None, max_length=120)
    fecha_entrega: date
    observaciones: Optional[str] = None
    items: list[CotizacionLogisticaRemisionItemIn] = Field(min_length=1)


class CotizacionLogisticaRemisionItemOut(BaseModel):
    item_key: str
    id_producto: int
    codigo_producto: Optional[str] = None
    descripcion: Optional[str] = None
    marca: Optional[str] = None
    particion: int = 1
    nombre_particion: Optional[str] = None
    cantidad: int


class CotizacionLogisticaRemisionOut(BaseModel):
    id: int
    numero_remision: str
    fecha_entrega: date
    observaciones: Optional[str] = None
    creado_en: datetime
    creado_por_id: Optional[int] = None
    items: list[CotizacionLogisticaRemisionItemOut] = Field(default_factory=list)


class CotizacionLogisticaOrdenCompraSugeridaOut(BaseModel):
    marca: str
    unidades_pendientes: int
    productos: list[CotizacionLogisticaProductoOut] = Field(default_factory=list)


class CotizacionLogisticaResumenOut(BaseModel):
    cotizacion_id: int
    stock_estado: str
    porcentaje_stock: float
    total_unidades: int
    unidades_separadas: int
    unidades_entregadas: int
    unidades_pendientes: int
    productos: list[CotizacionLogisticaProductoOut] = Field(default_factory=list)
    remisiones: list[CotizacionLogisticaRemisionOut] = Field(default_factory=list)
    ordenes_compra_sugeridas: list[CotizacionLogisticaOrdenCompraSugeridaOut] = Field(default_factory=list)
