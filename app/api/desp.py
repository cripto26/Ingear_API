from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.empleado import Empleado
from app.core.security import decode_access_token, infer_role
from app.core.view_permissions import has_view_permission

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

def require_view_permissions(*permissions: str):
    required = {str(permission or "").strip().lower() for permission in permissions}
    required.discard("")

    def checker(current: Empleado = Depends(get_current_empleado)):
        if not required:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se configuraron permisos de vistas requeridos",
            )

        if any(has_view_permission(current, permission) for permission in required):
            return current

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado",
        )

    return checker


def require_any_access(*, roles: tuple[str, ...] = (), permissions: tuple[str, ...] = ()):
    allowed_roles = {str(role or "").strip().upper() for role in roles}
    allowed_permissions = {
        str(permission or "").strip().lower() for permission in permissions
    }
    allowed_permissions.discard("")

    def checker(current: Empleado = Depends(get_current_empleado)):
        current_role = infer_role(current.area, current.cargo)
        if current_role in allowed_roles:
            return current

        if any(has_view_permission(current, permission) for permission in allowed_permissions):
            return current

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado",
        )

    return checker
