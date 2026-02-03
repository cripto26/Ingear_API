from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    Date,
    Numeric,
    Text,
)
from app.db.base import Base
from sqlalchemy.orm import relationship


class Proyecto(Base):
    __tablename__ = "proyecto"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False)


    url_cuenta_cobro = Column(String(500), nullable=True)
    anticipo = Column(Numeric(14, 2), nullable=True)

    fecha_inicio = Column(Date, nullable=True)

    estado_logistica = Column(String(80), nullable=True)
    estado_contable = Column(String(80), nullable=True)
    estado_ingenieria = Column(String(80), nullable=True)
    estado_factura = Column(String(80), nullable=True)

    observacion = Column(Text, nullable=True)

    oportunidad_id = Column(Integer, ForeignKey("oportunidad.id"), nullable=True, index=True)

    oportunidad = relationship("Oportunidad", back_populates="proyecto")

    # 1:N con Cotizacion (porque Cotizacion.id_proyecto existe)
    cotizaciones = relationship("Cotizacion", back_populates="proyecto")

    # M:N
    empleados = relationship("Empleado", secondary="proyecto_empleado", back_populates="proyectos")
    clientes = relationship("Cliente", secondary="proyecto_cliente", back_populates="proyectos")
    despachos = relationship("Despacho", secondary="proyecto_despacho", back_populates="proyectos")
