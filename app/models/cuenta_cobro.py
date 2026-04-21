from sqlalchemy import BigInteger, Column, Integer, String

from app.db.base import Base


BIGINT = BigInteger().with_variant(Integer, "sqlite")


class CuentaCobro(Base):
    __tablename__ = "cuenta_cobro"

    id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    cliente_id = Column(BIGINT, nullable=True, index=True)
    cliente_nombre = Column(String(255), nullable=True)
    nit = Column(String(50), nullable=True)
    direccion = Column(String(255), nullable=True)
    telefono = Column(String(50), nullable=True)
    proyecto = Column(String(255), nullable=True)
    numero_contrato = Column(String(100), nullable=True)
    id_cotizacion = Column(BIGINT, nullable=True, index=True)
