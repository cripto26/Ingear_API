from sqlalchemy import String, Integer, Column, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class Contacto(Base):
    __tablename__ = "contacto"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("cliente.id"), nullable=True, index=True)
    empresa = Column(String(255), nullable=True)
    nombre = Column(String(255), nullable=True)
    telefono = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    ciudad = Column(String(120), nullable=True)

    cliente = relationship("Cliente", back_populates="contactos")
