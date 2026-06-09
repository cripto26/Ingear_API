


from sqlalchemy import (
    String,
    Integer,
    Column,
    ForeignKey,
    DateTime,
    Numeric,
    Text,
    Index,
)
from sqlalchemy.sql import func

from app.db.base import Base


class CotizacionVersion(Base):
    # Legacy cotizacion_versiones is owned by postgres and has an incorrect FK.
    __tablename__ = "cotizacion_versiones_v2"
    __table_args__ = (
        Index(
            "uq_cotizacion_versiones_v2_cotizacion_version",
            "cotizacion_id",
            "versiones",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    cotizacion_id = Column(
        Integer,
        ForeignKey("cotizacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_empleado = Column(Integer, ForeignKey("empleado.id"), nullable=False, index=True)
    id_oportunidad = Column(Integer, ForeignKey("oportunidad.id"), nullable=False, index=True)

    url_cotizacion = Column(String(500), nullable=True)
    tiempo_entrega = Column(String(120), nullable=True)
    nombre_cotizacion = Column(String(255), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tipo_cotizacion = Column(String(120), nullable=True)
    etapa_cotizacion = Column(String(120), nullable=True)
    forma_pago = Column(String(120), nullable=True)
    tipo_servicio = Column(String(50), nullable=True)
    estado = Column(String(50), nullable=True)
    trm = Column(Numeric(14, 4), nullable=True)
    sub_total = Column(Numeric(14, 2), nullable=True)
    total = Column(Numeric(15, 2), nullable=True)
    productos = Column(Text, nullable=True)
    versiones = Column(Integer, nullable=False)

