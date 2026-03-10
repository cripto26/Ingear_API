from datetime import datetime, timedelta, timezone
import unicodedata
import bcrypt
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException, status
from app.core.config import settings

def normalize(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", value or "")
    return raw.encode("ascii", "ignore").decode().lower().strip()

def infer_role(area: str | None, cargo: str | None = None) -> str:
    text = f"{normalize(area)} {normalize(cargo)}"
    if "gerencia" in text or "gerente" in text or "director" in text:
        return "GERENCIA"
    if "logistica" in text:
        return "LOGISTICA"
    if "ingenieria" in text:
        return "INGENIERIA"
    if "administr" in text:
        return "ADMINISTRACION"
    if "comercial" in text or "proyectos" in text or "costos" in text:
        return "COMERCIAL"
    return "OTRO"

def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")
