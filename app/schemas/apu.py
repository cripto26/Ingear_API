from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ApuItem(BaseModel):
    item: str
    qty: Decimal = Field(ge=0)
    valor_unitario: Decimal = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def parse_legacy_array(cls, value: Any):
        if isinstance(value, (list, tuple)):
            if len(value) < 3:
                raise ValueError("Cada item APU debe incluir item, qty y valor_unitario.")
            return {
                "item": value[0],
                "qty": value[1],
                "valor_unitario": value[2],
            }
        return value

    @field_validator("item")
    @classmethod
    def validate_item(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("El nombre del item es obligatorio.")
        return normalized


class ApuBase(BaseModel):
    subtipo: str
    items: list[ApuItem] = Field(min_length=1)

    @field_validator("subtipo")
    @classmethod
    def validate_subtipo(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("El subtipo es obligatorio.")
        return normalized


class ApuCreate(ApuBase):
    pass


class ApuUpdate(BaseModel):
    subtipo: str | None = None
    items: list[ApuItem] | None = Field(default=None, min_length=1)

    @field_validator("subtipo")
    @classmethod
    def validate_subtipo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("El subtipo es obligatorio.")
        return normalized


class ApuOut(ApuBase):
    valor_total: Decimal

    class Config:
        from_attributes = True
