from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_refresh_session import AuthRefreshSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_refresh_expiry() -> datetime:
    return utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def hash_refresh_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def create_refresh_session(db: Session, empleado_id: int) -> str:
    timestamp = utc_now()
    raw_token = token_urlsafe(48)
    session = AuthRefreshSession(
        empleado_id=empleado_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=build_refresh_expiry(),
        created_at=timestamp,
        last_used_at=timestamp,
        revoked_at=None,
    )
    db.add(session)
    db.commit()
    return raw_token


def find_active_refresh_session(
    db: Session,
    raw_token: str | None,
) -> AuthRefreshSession | None:
    token = (raw_token or "").strip()
    if not token:
        return None

    stmt = select(AuthRefreshSession).where(
        AuthRefreshSession.token_hash == hash_refresh_token(token)
    )
    session = db.execute(stmt).scalar_one_or_none()
    if not session:
        return None

    now = utc_now()
    if session.revoked_at is not None or session.expires_at <= now:
        return None

    return session


def rotate_refresh_session(db: Session, session: AuthRefreshSession) -> str:
    raw_token = token_urlsafe(48)
    session.token_hash = hash_refresh_token(raw_token)
    session.last_used_at = utc_now()
    session.expires_at = build_refresh_expiry()
    db.add(session)
    db.commit()
    return raw_token


def revoke_refresh_session(db: Session, raw_token: str | None) -> None:
    session = find_active_refresh_session(db, raw_token)
    if not session:
        return

    session.revoked_at = utc_now()
    db.add(session)
    db.commit()


def revoke_refresh_sessions_for_empleado(db: Session, empleado_id: int) -> None:
    now = utc_now()
    stmt = select(AuthRefreshSession).where(
        AuthRefreshSession.empleado_id == empleado_id,
        AuthRefreshSession.revoked_at.is_(None),
    )
    sessions = db.execute(stmt).scalars().all()
    if not sessions:
        return

    for session in sessions:
        session.revoked_at = now
        db.add(session)

    db.commit()
