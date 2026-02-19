# app/schemas/pais.py
from decimal import Decimal
from pydantic import BaseModel, Field


class PaisBase(BaseModel):
    pais: str = Field(..., max_length=120)
    valor_peso_kilogramo: Decimal
    gasto_en_origen: Decimal


class PaisCreate(PaisBase):
    pass


class PaisUpdate(BaseModel):
    # PK no se actualiza
    valor_peso_kilogramo: Decimal | None = None
    gasto_en_origen: Decimal | None = None


class PaisOut(PaisBase):
    class Config:
        from_attributes = True
