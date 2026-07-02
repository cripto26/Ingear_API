from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CotizacionAprobada(Base):
    __tablename__ = "cotizaciones_aprobada"

    id = Column(Integer, ForeignKey("cotizacion.id"), primary_key=True, index=True)
    id_empleado = Column(Integer, ForeignKey("empleado.id"), nullable=False, index=True)
    id_oportunidad = Column(Integer, ForeignKey("oportunidad.id"), nullable=False, index=True)

    url_cotizacion = Column(String(500), nullable=True)
    tiempo_entrega = Column(String(120), nullable=True)
    nombre_cotizacion = Column(String(255), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), nullable=False)
    fecha_aprobacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tipo_cotizacion = Column(String(120), nullable=True)
    etapa_cotizacion = Column(String(120), nullable=True)
    forma_pago = Column(String(120), nullable=True)
    contacto = Column(String(255), nullable=True)
    tipo_servicio = Column(String(50), nullable=True)
    trm = Column(Numeric(14, 4), nullable=True)
    sub_total = Column(Numeric(14, 2), nullable=True)
    total = Column(Numeric(15, 2), nullable=True)
    productos = Column(Text, nullable=True)
    estado = Column(String(50), nullable=True, default="2")

    logistica_stock = Column(Integer, nullable=True, default=0)
    logistica_stock_estado = Column(String(30), nullable=True, default="incompleto")
    logistica_fecha_despacho = Column(Date, nullable=True)
    logistica_fecha_entrega = Column(Date, nullable=True)
    logistica_remision = Column(String(120), nullable=True)
    logistica_unidades_pendientes = Column(Integer, nullable=True)
    logistica_orden_compra = Column(String(120), nullable=True)
    logistica_observaciones = Column(Text, nullable=True)

    empleado = relationship("Empleado", foreign_keys=[id_empleado])
    oportunidad = relationship("Oportunidad", foreign_keys=[id_oportunidad])
    cotizacion = relationship("Cotizacion", foreign_keys=[id])

    @property
    def empleado_nombre(self):
        override = getattr(self, "_empleado_nombre_override", None)
        if override:
            return override
        return self.empleado.nombre if self.empleado else None

    @empleado_nombre.setter
    def empleado_nombre(self, value):
        self._empleado_nombre_override = value

    @property
    def proyecto_nombre(self):
        return self.oportunidad.nombre_proyecto if self.oportunidad else None


class CotizacionLogisticaSeparacion(Base):
    __tablename__ = "cotizacion_logistica_separacion"

    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones_aprobada.id"), nullable=False, index=True)
    id_producto = Column(Integer, ForeignKey("producto.id"), nullable=False, index=True)
    item_key = Column(String(180), nullable=False)
    particion = Column(Integer, nullable=False, default=1)
    nombre_particion = Column(String(120), nullable=True)
    cantidad_cotizada = Column(Integer, nullable=False, default=0)
    cantidad_separada = Column(Integer, nullable=False, default=0)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(Integer, ForeignKey("empleado.id"), nullable=True)
    actualizado_por_id = Column(Integer, ForeignKey("empleado.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "cotizacion_id",
            "item_key",
            name="uq_cotizacion_logistica_separacion_item",
        ),
    )


class CotizacionLogisticaRemision(Base):
    __tablename__ = "cotizacion_logistica_remision"

    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones_aprobada.id"), nullable=False, index=True)
    numero_remision = Column(String(120), nullable=False)
    fecha_entrega = Column(Date, nullable=False)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(Integer, ForeignKey("empleado.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship(
        "CotizacionLogisticaRemisionItem",
        back_populates="remision",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "cotizacion_id",
            "numero_remision",
            name="uq_cotizacion_logistica_remision_numero",
        ),
    )


class CotizacionLogisticaRemisionItem(Base):
    __tablename__ = "cotizacion_logistica_remision_item"

    id = Column(Integer, primary_key=True, index=True)
    remision_id = Column(
        Integer,
        ForeignKey("cotizacion_logistica_remision.id"),
        nullable=False,
        index=True,
    )
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones_aprobada.id"), nullable=False, index=True)
    id_producto = Column(Integer, ForeignKey("producto.id"), nullable=False, index=True)
    item_key = Column(String(180), nullable=False)
    particion = Column(Integer, nullable=False, default=1)
    nombre_particion = Column(String(120), nullable=True)
    cantidad = Column(Integer, nullable=False)

    remision = relationship(
        "CotizacionLogisticaRemision",
        back_populates="items",
    )
