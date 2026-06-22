from decimal import Decimal
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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
    model_config = ConfigDict(populate_by_name=True)

    tipo_producto: str = Field(
        validation_alias=AliasChoices("tipo_producto", "subtipo")
    )
    categoria: str | None = None
    items: list[ApuItem] = Field(min_length=1)

    @field_validator("tipo_producto")
    @classmethod
    def validate_tipo_producto(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("El tipo de producto es obligatorio.")
        return normalized

    @field_validator("categoria")
    @classmethod
    def validate_categoria(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip()
        return normalized or None


class ApuCreate(ApuBase):
    pass


class ApuUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tipo_producto: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tipo_producto", "subtipo"),
    )
    categoria: str | None = None
    items: list[ApuItem] | None = Field(default=None, min_length=1)

    @field_validator("tipo_producto")
    @classmethod
    def validate_tipo_producto(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("El tipo de producto es obligatorio.")
        return normalized

    @field_validator("categoria")
    @classmethod
    def validate_categoria(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip()
        return normalized or None


class ApuOut(ApuBase):
    valor_total: Decimal

    class Config:
        from_attributes = True
