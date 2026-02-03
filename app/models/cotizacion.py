from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    DateTime,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from app.db.base import Base
from sqlalchemy.orm import relationship



class Cotizacion(Base):
    __tablename__ = "cotizacion"

    id = Column(Integer, primary_key=True, index=True)
    consecutivo = Column(String(60), nullable=False, index=True)

    id_cotizador = Column(Integer, ForeignKey("empleado.id"), nullable=False, index=True)
    id_proyecto = Column(Integer, ForeignKey("proyecto.id"), nullable=False, index=True)
    
    

    url_cotizacion = Column(String(500), nullable=True)

   
    tiempo_entrega = Column(String(120), nullable=True)
    nombre_cotizacion = Column(String(255), nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tipo_cotizacion = Column(String(120), nullable=True)
    etapa_cotizacion = Column(String(120), nullable=True)
    forma_pago = Column(String(120), nullable=True)

    total = Column(Numeric(14, 2), nullable=True)

    cotizador = relationship("Empleado", back_populates="cotizaciones", foreign_keys=[id_cotizador])
    proyecto = relationship("Proyecto", back_populates="cotizaciones", foreign_keys=[id_proyecto])

    __table_args__ = (
        UniqueConstraint("consecutivo", name="uq_cotizacion_consecutivo"),
    )
