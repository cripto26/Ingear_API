from sqlalchemy import Column, JSON, Numeric, String

from app.db.base import Base


class Apu(Base):
    __tablename__ = "apu"

    tipo_producto = Column(String(120), primary_key=True, index=True)
    categoria = Column(String(120), nullable=True, index=True)
    items = Column(JSON, nullable=False)
    valor_total = Column(Numeric(14, 2), nullable=False)
