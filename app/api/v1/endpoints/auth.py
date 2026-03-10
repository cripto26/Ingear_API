from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.crud.empleado import crud_empleado
from app.schemas.auth import LoginIn, TokenOut, AuthUserOut
from app.core.security import verify_password, create_access_token, infer_role
from app.api.deps import get_current_empleado

router = APIRouter()

def to_auth_user(emp) -> AuthUserOut:
    return AuthUserOut(
        id=emp.id, nombre=emp.nombre, email=emp.email, cargo=emp.cargo,
        area=emp.area, estado=emp.estado, role=infer_role(emp.area, emp.cargo),
    )

@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    empleado = crud_empleado.get_by_login(db, payload.username)
    if not empleado or not verify_password(payload.password, empleado.contrasena):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
    if (empleado.estado or "").strip().lower() != "activo":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta inactiva")
    token = create_access_token(str(empleado.id))
    return TokenOut(access_token=token, user=to_auth_user(empleado))

@router.get("/me", response_model=AuthUserOut)
def me(current = Depends(get_current_empleado)):
    return to_auth_user(current)
