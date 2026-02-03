from pydantic import BaseModel, EmailStr
from typing import Optional


class ClienteBase(BaseModel):
    razon_social: str
    nit: str
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    world_office_id: str
    tipo_contribuyente: Optional[str] = None
    actividad_economica: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    razon_social: Optional[str] = None
    nit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    world_office_id: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    actividad_economica: Optional[str] = None


class ClienteOut(ClienteBase):
    id: int

    class Config:
        from_attributes = True
