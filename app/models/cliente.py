from sqlalchemy import String, Integer, Column, UniqueConstraint, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship


class Cliente(Base):
    __tablename__ = "cliente"

    id = Column(Integer, primary_key=True, index=True)
    razon_social = Column(String(255), nullable=False)
    nit = Column(String(50), nullable=False, index=True)
    telefono = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    direccion = Column(String(255), nullable=True)
    ciudad = Column(String(120), nullable=True)

    world_office_id = Column(String(80), nullable=False)
    tipo_contribuyente = Column(String(120), nullable=True)
    actividad_economica = Column(String(200), nullable=True)

    oportunidades = relationship("Oportunidad", back_populates="cliente", cascade="all, delete-orphan")
    # M:N con Proyecto vía tabla puente
    proyectos = relationship("Proyecto", secondary="proyecto_cliente", back_populates="clientes")

    __table_args__ = (
        UniqueConstraint("nit", name="uq_cliente_nit"),
    )
