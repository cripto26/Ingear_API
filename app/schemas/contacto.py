from pydantic import BaseModel
from typing import Optional


class ContactoBase(BaseModel):
    empresa: Optional[str] = None
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None


class ContactoCreate(ContactoBase):
    cliente_id: int


class ContactoUpdate(ContactoBase):
    cliente_id: Optional[int] = None


class ContactoOut(ContactoBase):
    id: int
    cliente_id: Optional[int] = None

    class Config:
        from_attributes = True
