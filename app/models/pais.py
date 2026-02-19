from sqlalchemy import String, Column, Numeric
from app.db.base import Base


class Pais(Base):
    __tablename__ = "pais"

    # En tu BD: pais es PK (varchar(120))
    pais = Column(String(120), primary_key=True, index=True)

    # En tu BD:
    # valor_peso_kilogramo numeric(14,4)
    # gasto_en_origen numeric(14,2)
    valor_peso_kilogramo = Column(Numeric(14, 4), nullable=True)
    gasto_en_origen = Column(Numeric(14, 2), nullable=True)
