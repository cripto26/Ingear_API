from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    Date,
    Numeric,
)
from app.db.base import Base
from sqlalchemy.orm import relationship


class Oportunidad(Base):
    __tablename__ = "oportunidad"

    id = Column(Integer, primary_key=True, index=True)

    cliente_id = Column(Integer, ForeignKey("cliente.id"), nullable=False, index=True)

    nombre_proyecto = Column(String(255), nullable=True)
    tipologia = Column(String(120), nullable=True)
    tipo_contacto = Column(String(120), nullable=True)
    ciudad = Column(String(120), nullable=True)
    tipo_servicio = Column(String(120), nullable=True)

    # En el ER aparece como "responsable_cotizacion" (relación a EMPLEADO)
    responsable_cotizacion = Column(Integer, ForeignKey("empleado.id"), nullable=False, index=True)

    marca_predominante = Column(String(120), nullable=True)

    fecha_oportunidad = Column(Date, nullable=False)
    fecha_cotizacion = Column(Date, nullable=True)

    rubro_sin_iva = Column(Numeric(14, 2), nullable=True)
    nivel_importancia = Column(String(50), nullable=True)
    porcentaje_cierre = Column(Numeric(5, 2), nullable=True)
    fecha_cierre = Column(Date, nullable=True)

    cliente = relationship("Cliente", back_populates="oportunidades")

    responsable = relationship(
        "Empleado",
        back_populates="oportunidades_responsable",
        foreign_keys=[responsable_cotizacion],
    )

    # Proyecto asociado (si tu ER lo piensa 1:1, mira la nota de UNIQUE abajo)
    proyecto = relationship("Proyecto", back_populates="oportunidad", uselist=False)
