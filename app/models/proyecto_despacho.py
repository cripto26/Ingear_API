from sqlalchemy import Integer, Column, ForeignKey
from app.db.base import Base


class ProyectoDespacho(Base):
    __tablename__ = "proyecto_despacho"

    id_despacho = Column(Integer, ForeignKey("despachos.id"), primary_key=True)
    id_proyecto = Column(Integer, ForeignKey("proyecto.id"), primary_key=True)
