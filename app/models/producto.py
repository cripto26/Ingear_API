from sqlalchemy import (
    String,
    Integer,
    Column,
    Date,
    Numeric,
    UniqueConstraint,
)
from app.db.base import Base


class Producto(Base):
    __tablename__ = "producto"

    id = Column(Integer, primary_key=True, index=True)

    codigo_producto = Column(String(80), nullable=False, index=True)
    marca = Column(String(120), nullable=True)
    descripcion = Column(String(500), nullable=True)

    costo_instalacion = Column(Numeric(14, 2), nullable=True)
    costo_fabrica = Column(Numeric(14, 2), nullable=True)
    descuento_fabricante = Column(Numeric(8, 2), nullable=True)

    pais_origen = Column(String(120), nullable=True)
    costo_ingear = Column(Numeric(14, 2), nullable=True)

    fecha_creacion_producto = Column(Date, nullable=True)

    url_imagen = Column(String(500), nullable=True)
    url_ficha_tecnica = Column(String(500), nullable=True)

    peso_kg = Column(Numeric(10, 3), nullable=True)
    volumen = Column(Numeric(12, 4), nullable=True)

    valor_inventario = Column(Numeric(14, 2), nullable=True)

    tipo_producto = Column(String(120), nullable=True)
    subtipo = Column(String(120), nullable=True)

    moneda = Column(String(20), nullable=True)
    arancel = Column(Numeric(8, 2), nullable=True)

    referencia = Column(String(120), nullable=True)
    categoria = Column(String(120), nullable=True)

    # En tu última versión: inventario vive dentro del producto
    cantidad_inventario = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("codigo_producto", name="uq_producto_codigo"),
    )
