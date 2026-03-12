from typing import Literal, Optional
from pydantic import BaseModel, EmailStr

class LoginIn(BaseModel):
    username: str
    password: str

class AuthUserOut(BaseModel):
    id: int
    nombre: str
    email: Optional[EmailStr] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    estado: Optional[str] = None
    role: Literal["COMERCIAL", "ADMINISTRACION", "LOGISTICA", "INGENIERIA", "GERENCIA", "OTRO"]

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class MessageOut(BaseModel):
    message: str
