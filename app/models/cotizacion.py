from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    DateTime,
    Numeric,
    Text,
)
from sqlalchemy.sql import func
from app.db.base import Base
from sqlalchemy.orm import relationship


class Cotizacion(Base):
    __tablename__ = "cotizacion"

    id = Column(Integer, primary_key=True, index=True)

    id_empleado = Column(Integer, ForeignKey("empleado.id"), nullable=False, index=True)
    id_oportunidad = Column(Integer, ForeignKey("oportunidad.id"), nullable=False, index=True)

    url_cotizacion = Column(String(500), nullable=True)
    tiempo_entrega = Column(String(120), nullable=True)
    nombre_cotizacion = Column(String(255), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tipo_cotizacion = Column(String(120), nullable=True)
    etapa_cotizacion = Column(String(120), nullable=True)
    forma_pago = Column(String(120), nullable=True)
    tipo_servicio = Column(String(50), nullable=True)
    sub_total = Column(Numeric(14, 2), nullable=True)
    total = Column(Numeric(15, 2), nullable=True)
    productos = Column(Text, nullable=True)
    estado = Column(String(50), nullable=True)

    empleado = relationship("Empleado", back_populates="cotizaciones", foreign_keys=[id_empleado])
    oportunidad = relationship("Oportunidad", foreign_keys=[id_oportunidad])
