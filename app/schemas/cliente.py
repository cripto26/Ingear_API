from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional


class ClienteBase(BaseModel):
    razon_social: Optional[str] = None
    nit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    world_office_id: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    actividad_economica: Optional[str] = None
    contacto_id: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    empleado_id: Optional[int] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(ClienteBase):
    pass


class ClienteOut(ClienteBase):
    id: int

    class Config:
        from_attributes = True
