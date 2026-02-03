from sqlalchemy import (
    String,
    Integer,
    Column,
    Date,
    Numeric,
)
from app.db.base import Base
from sqlalchemy.orm import relationship


class Despacho(Base):
    __tablename__ = "despachos"

    id = Column(Integer, primary_key=True, index=True)

    fecha = Column(Date, nullable=False)
    transportadora = Column(String(120), nullable=True)
    guia = Column(String(120), nullable=True)

    valor_flete_seguro = Column(Numeric(14, 2), nullable=True)
    valor_mercancia = Column(Numeric(14, 2), nullable=True)

    ciudad_origen = Column(String(120), nullable=True)
    contacto = Column(String(150), nullable=True)

    estado = Column(String(80), nullable=True)
    ciudad_destino = Column(String(120), nullable=True)

    proyectos = relationship("Proyecto", secondary="proyecto_despacho", back_populates="despachos")
