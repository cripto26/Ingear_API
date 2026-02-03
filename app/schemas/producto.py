from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal


class ProductoBase(BaseModel):
    codigo_producto: str
    marca: Optional[str] = None
    descripcion: Optional[str] = None
    costo_instalacion: Optional[Decimal] = None
    costo_fabrica: Optional[Decimal] = None
    descuento_fabricante: Optional[Decimal] = None
    pais_origen: Optional[str] = None
    costo_ingear: Optional[Decimal] = None
    fecha_creacion_producto: Optional[date] = None
    url_imagen: Optional[str] = None
    url_ficha_tecnica: Optional[str] = None
    peso_kg: Optional[Decimal] = None
    volumen: Optional[Decimal] = None
    valor_inventario: Optional[Decimal] = None
    tipo_producto: Optional[str] = None
    subtipo: Optional[str] = None
    moneda: Optional[str] = None
    arancel: Optional[Decimal] = None
    cantidad_inventario: int = 0


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
    costo_ingear: Optional[Decimal] = None
    fecha_creacion_producto: Optional[date] = None
    url_imagen: Optional[str] = None
    url_ficha_tecnica: Optional[str] = None
    peso_kg: Optional[Decimal] = None
    volumen: Optional[Decimal] = None
    valor_inventario: Optional[Decimal] = None
    tipo_producto: Optional[str] = None
    subtipo: Optional[str] = None
    moneda: Optional[str] = None
    arancel: Optional[Decimal] = None
    cantidad_inventario: Optional[int] = None


class ProductoOut(ProductoBase):
    id: int

    class Config:
        from_attributes = True
