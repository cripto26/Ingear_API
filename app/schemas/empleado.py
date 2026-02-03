from pydantic import BaseModel, EmailStr
from typing import Optional


class EmpleadoBase(BaseModel):
    nombre: str
    email: Optional[EmailStr] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    estado: Optional[str] = None
    cedula: Optional[str] = None
    telefono: Optional[str] = None


class EmpleadoCreate(EmpleadoBase):
    pass


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    estado: Optional[str] = None
    cedula: Optional[str] = None
    telefono: Optional[str] = None


class EmpleadoOut(EmpleadoBase):
    id: int

    class Config:
        from_attributes = True
