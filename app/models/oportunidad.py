from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    Date,
    Numeric,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Oportunidad(Base):
    __tablename__ = "oportunidad"

    id = Column(Integer, primary_key=True, index=True)

    cliente_id = Column(Integer, ForeignKey("cliente.id"), nullable=True, index=True)

    nombre_proyecto = Column(String(255), nullable=True)
    tipo_contacto = Column(String(120), nullable=True)
    ciudad = Column(String(120), nullable=True)
    tipo_servicio = Column(String(120), nullable=True)

    responsable_cotizacion = Column(
        Integer, ForeignKey("empleado.id"), nullable=True, index=True
    )

    marca_predominante = Column(String(120), nullable=True)

    fecha_oportunidad = Column(Date, nullable=True)
    fecha_cotizacion = Column(Date, nullable=True)

    rubro_sin_iva = Column(Numeric(14, 2), nullable=True)
    nivel_importancia = Column(String(50), nullable=True)
    porcentaje_cierre = Column(String(50), nullable=True)
    fecha_cierre = Column(Date, nullable=True)
    segmento = Column(String(120), nullable=True)
    cotizaciones = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    numero_empleado = Column(Integer, nullable=True)
    nuevo_existente = Column(String(120), nullable=True)

    cliente = relationship("Cliente", back_populates="oportunidades")

    responsable = relationship(
        "Empleado",
        back_populates="oportunidades_responsable",
        foreign_keys=[responsable_cotizacion],
    )

    proyecto = relationship("Proyecto", back_populates="oportunidad", uselist=False)
