from sqlalchemy import Integer, Column, ForeignKey
from app.db.base import Base


class ProyectoCliente(Base):
    __tablename__ = "proyecto_cliente"

    id_cliente = Column(Integer, ForeignKey("cliente.id"), primary_key=True)
    id_proyecto = Column(Integer, ForeignKey("proyecto.id"), primary_key=True)
