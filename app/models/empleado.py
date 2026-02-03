from sqlalchemy import String, Integer, Column, UniqueConstraint
from app.db.base import Base
from sqlalchemy.orm import relationship

class Empleado(Base):
    __tablename__ = "empleado"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    cargo = Column(String(120), nullable=True)
    area = Column(String(120), nullable=True)
    estado = Column(String(50), nullable=True)
    cedula = Column(String(50), nullable=True, index=True)
    telefono = Column(String(50), nullable=True)

    cotizaciones = relationship("Cotizacion", back_populates="cotizador")

    oportunidades_responsable = relationship(
        "Oportunidad",
        back_populates="responsable",
        foreign_keys="Oportunidad.responsable_cotizacion",
    )

    proyectos = relationship("Proyecto", secondary="proyecto_empleado", back_populates="empleados")

    __table_args__ = (
        UniqueConstraint("cedula", name="uq_empleado_cedula"),
    )
