from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional

from app.core.view_permissions import (
    COMMERCIAL_VIEW_PERMISSION_ALLOWED_SET,
    normalize_view_permissions,
)


class EmpleadoBase(BaseModel):
    nombre: str
    email: Optional[EmailStr] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    estado: Optional[str] = None
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    jefe_id: Optional[int] = None
    permisos_vistas: Optional[list[str]] = None

    @field_validator("permisos_vistas")
    @classmethod
    def validate_permisos_vistas(cls, value: Optional[list[str]]):
        normalized = normalize_view_permissions(value)
        if normalized is None:
            return None

        invalid = [
            item
            for item in normalized
            if item not in COMMERCIAL_VIEW_PERMISSION_ALLOWED_SET
        ]
        if invalid:
            raise ValueError("Hay permisos de vistas no permitidos.")

        return normalized


class EmpleadoCreate(EmpleadoBase):
    contrasena: str


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    estado: Optional[str] = None
    cedula: str
    telefono: Optional[str] = None
    jefe_id: Optional[int] = None
    permisos_vistas: Optional[list[str]] = None
    contrasena: Optional[str] = None

    @field_validator("permisos_vistas")
    @classmethod
    def validate_update_permisos_vistas(cls, value: Optional[list[str]]):
        normalized = normalize_view_permissions(value)
        if normalized is None:
            return None

        invalid = [
            item
            for item in normalized
            if item not in COMMERCIAL_VIEW_PERMISSION_ALLOWED_SET
        ]
        if invalid:
            raise ValueError("Hay permisos de vistas no permitidos.")

        return normalized


class EmpleadoOut(EmpleadoBase):
    id: int

    class Config:
        from_attributes = True
