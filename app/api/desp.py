from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.empleado import Empleado
from app.core.security import decode_access_token, infer_role

bearer = HTTPBearer(auto_error=False)

def get_current_empleado(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="No autenticado")
    payload = decode_access_token(credentials.credentials)
    empleado = db.get(Empleado, int(payload["sub"]))
    if not empleado:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return empleado

def require_roles(*roles: str):
    def checker(current: Empleado = Depends(get_current_empleado)):
        role = infer_role(current.area, current.cargo)
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
        return current
    return checker
