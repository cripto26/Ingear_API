from sqlalchemy import Integer, Column, ForeignKey
from app.db.base import Base


class ProyectoEmpleado(Base):
    __tablename__ = "proyecto_empleado"

    id_empleado = Column(Integer, ForeignKey("empleado.id"), primary_key=True)
    id_proyecto = Column(Integer, ForeignKey("proyecto.id"), primary_key=True)
