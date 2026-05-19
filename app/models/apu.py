from sqlalchemy import Column, JSON, Numeric, String

from app.db.base import Base


class Apu(Base):
    __tablename__ = "apu"

    subtipo = Column(String(120), primary_key=True, index=True)
    items = Column(JSON, nullable=False)
    valor_total = Column(Numeric(14, 2), nullable=False)
