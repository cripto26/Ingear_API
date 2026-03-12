from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.crud.empleado import crud_empleado
from app.schemas.auth import LoginIn, TokenOut, AuthUserOut, ChangePasswordIn, MessageOut
from app.core.security import verify_password, create_access_token, infer_role, hash_password

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

@router.post("/change-password", response_model=MessageOut)
def change_password(
    payload: ChangePasswordIn,
    current = Depends(get_current_empleado),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current.contrasena):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La contrasena actual es incorrecta"
        )

    new_password = (payload.new_password or "").strip()

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contrasena debe tener al menos 8 caracteres"
        )

    if verify_password(new_password, current.contrasena):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contrasena no puede ser igual a la actual"
        )

    current.contrasena = hash_password(new_password)
    db.add(current)
    db.commit()

    return MessageOut(message="Contrasena actualizada correctamente")


