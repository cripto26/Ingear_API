from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Notificacion(Base):
    __tablename__ = "notificacion"

    id = Column(Integer, primary_key=True, index=True)
    destinatario_empleado_id = Column(
        Integer,
        ForeignKey("empleado.id"),
        nullable=False,
        index=True,
    )
    actor_empleado_id = Column(
        Integer,
        ForeignKey("empleado.id"),
        nullable=True,
        index=True,
    )
    tipo = Column(String(120), nullable=False, index=True)
    area = Column(String(120), nullable=True)
    titulo = Column(String(255), nullable=False)
    mensaje = Column(Text, nullable=True)
    entidad_tipo = Column(String(80), nullable=True, index=True)
    entidad_id = Column(Integer, nullable=True, index=True)
    ruta_destino = Column(String(500), nullable=True)
    requiere_accion = Column(Boolean, nullable=False, default=False)
    leida_en = Column(DateTime(timezone=True), nullable=True)
    resuelta_en = Column(DateTime(timezone=True), nullable=True)
    fecha_creacion = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    destinatario = relationship(
        "Empleado",
        foreign_keys=[destinatario_empleado_id],
    )
    actor = relationship("Empleado", foreign_keys=[actor_empleado_id])
