from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_empleado
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    infer_role,
    verify_password,
)
from app.crud.empleado import crud_empleado
from app.db.session import get_db
from app.schemas.auth import (
    AuthUserOut,
    ChangePasswordIn,
    LoginIn,
    PasswordChangeOut,
    TokenOut,
)
from app.services.auth_session_service import (
    create_refresh_session,
    find_active_refresh_session,
    revoke_refresh_session,
    revoke_refresh_sessions_for_empleado,
    rotate_refresh_session,
)

router = APIRouter()


def to_auth_user(emp) -> AuthUserOut:
    return AuthUserOut(
        id=emp.id,
        nombre=emp.nombre,
        email=emp.email,
        cargo=emp.cargo,
        area=emp.area,
        estado=emp.estado,
        permisos_vistas=emp.permisos_vistas,
        role=infer_role(emp.area, emp.cargo),
    )


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


def get_refresh_token_from_request(request: Request) -> str | None:
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    response: Response,
    db: Session = Depends(get_db),
):
    empleado = crud_empleado.get_by_login(db, payload.username)
    if not empleado or not verify_password(payload.password, empleado.contrasena):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )
    if (empleado.estado or "").strip().lower() != "activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva",
        )

    access_token = create_access_token(str(empleado.id))
    refresh_token = create_refresh_session(db, empleado.id)
    set_refresh_cookie(response, refresh_token)

    return TokenOut(access_token=access_token, user=to_auth_user(empleado))


@router.post("/refresh", response_model=TokenOut)
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    refresh_token = get_refresh_token_from_request(request)
    session = find_active_refresh_session(db, refresh_token)
    if not session:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion expirada",
        )

    empleado = crud_empleado.get(db, session.empleado_id)
    if not empleado or (empleado.estado or "").strip().lower() != "activo":
        clear_refresh_cookie(response)
        if empleado:
            revoke_refresh_sessions_for_empleado(db, empleado.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion no valida",
        )

    next_refresh_token = rotate_refresh_session(db, session)
    set_refresh_cookie(response, next_refresh_token)

    return TokenOut(
        access_token=create_access_token(str(empleado.id)),
        user=to_auth_user(empleado),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    revoke_refresh_session(db, get_refresh_token_from_request(request))
    clear_refresh_cookie(response)
    return None


@router.get("/me", response_model=AuthUserOut)
def me(current=Depends(get_current_empleado)):
    return to_auth_user(current)


@router.post("/change-password", response_model=PasswordChangeOut)
def change_password(
    payload: ChangePasswordIn,
    response: Response,
    current=Depends(get_current_empleado),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current.contrasena):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La contrasena actual es incorrecta",
        )

    new_password = (payload.new_password or "").strip()

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contrasena debe tener al menos 8 caracteres",
        )

    if verify_password(new_password, current.contrasena):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contrasena no puede ser igual a la actual",
        )

    current.contrasena = hash_password(new_password)
    db.add(current)
    db.commit()
    db.refresh(current)

    revoke_refresh_sessions_for_empleado(db, current.id)
    next_refresh_token = create_refresh_session(db, current.id)
    set_refresh_cookie(response, next_refresh_token)

    return PasswordChangeOut(
        message="Contrasena actualizada correctamente",
        access_token=create_access_token(str(current.id)),
        user=to_auth_user(current),
    )
