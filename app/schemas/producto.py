from pydantic import BaseModel, model_validator
from typing import Any, Optional
from datetime import date
from decimal import Decimal


def _normalize_producto_field_names(value: Any) -> Any:
    if not isinstance(value, dict) or "subtipo" not in value:
        return value

    data = dict(value)
    old_tipo_producto = data.get("tipo_producto")
    old_subtipo = data.pop("subtipo", None)
    data["categoria"] = old_tipo_producto
    data["tipo_producto"] = old_subtipo
    return data


class ProductoBase(BaseModel):
    codigo_producto: str
    marca: Optional[str] = None
    descripcion: Optional[str] = None
    costo_instalacion: Optional[Decimal] = None
    costo_fabrica: Optional[Decimal] = None
    descuento_fabricante: Optional[Decimal] = None
    pais_origen: Optional[str] = None
    ciudad: Optional[str] = None
    costo_ingear: Optional[Decimal] = None
    fecha_creacion_producto: Optional[date] = None
    url_imagen: Optional[str] = None
    url_imagen_dimension: Optional[str] = None
    url_ficha_tecnica: Optional[str] = None
    precio_pvp: Optional[Decimal] = None
    peso_kg: Optional[Decimal] = None
    volumen: Optional[Decimal] = None
    valor_inventario: Optional[Decimal] = None
    precio_inventario: Optional[Decimal] = None
    categoria: Optional[str] = None
    tipo_producto: Optional[str] = None
    moneda: Optional[str] = None
    arancel: Optional[Decimal] = None
    cantidad_inventario: int = 0
    referencia: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_field_names(cls, value: Any) -> Any:
        return _normalize_producto_field_names(value)


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    codigo_producto: Optional[str] = None
    marca: Optional[str] = None
    descripcion: Optional[str] = None
    costo_instalacion: Optional[Decimal] = None
    costo_fabrica: Optional[Decimal] = None
    descuento_fabricante: Optional[Decimal] = None
    pais_origen: Optional[str] = None
    ciudad: Optional[str] = None
    costo_ingear: Optional[Decimal] = None
    fecha_creacion_producto: Optional[date] = None
    url_imagen: Optional[str] = None
    url_imagen_dimension: Optional[str] = None
    url_ficha_tecnica: Optional[str] = None
    precio_pvp: Optional[Decimal] = None
    peso_kg: Optional[Decimal] = None
    volumen: Optional[Decimal] = None
    valor_inventario: Optional[Decimal] = None
    precio_inventario: Optional[Decimal] = None
    categoria: Optional[str] = None
    tipo_producto: Optional[str] = None
    moneda: Optional[str] = None
    arancel: Optional[Decimal] = None
    cantidad_inventario: Optional[int] = None
    referencia: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_field_names(cls, value: Any) -> Any:
        return _normalize_producto_field_names(value)


class ProductoOut(ProductoBase):
    id: int

    class Config:
        from_attributes = True


class WorldOfficeInventoryStatusOut(BaseModel):
    enabled: bool
    configured: bool
    connected: bool
    database: Optional[str] = None
    bodega_codigo: Optional[str] = None
    error: Optional[str] = None


class WorldOfficeInventorySyncOut(BaseModel):
    total_productos: int
    matched_productos: int
    unmatched_productos: int
    updated_productos: int
    updated_cantidades: int
    updated_precios: int
    database: Optional[str] = None
    bodega_codigo: Optional[str] = None


class WorldOfficeProductImportOut(BaseModel):
    productos_worldoffice: int
    productos_existentes: int
    productos_importados: int
    database: Optional[str] = None
    bodega_codigo: Optional[str] = None
