from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notificacion import Notificacion


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_notification(
    db: Session,
    *,
    destinatario_empleado_id: int,
    tipo: str,
    titulo: str,
    actor_empleado_id: int | None = None,
    area: str | None = None,
    mensaje: str | None = None,
    entidad_tipo: str | None = None,
    entidad_id: int | None = None,
    ruta_destino: str | None = None,
    requiere_accion: bool = False,
) -> Notificacion:
    notification = Notificacion(
        destinatario_empleado_id=destinatario_empleado_id,
        actor_empleado_id=actor_empleado_id,
        tipo=tipo,
        area=area,
        titulo=titulo,
        mensaje=mensaje,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        ruta_destino=ruta_destino,
        requiere_accion=requiere_accion,
    )
    db.add(notification)
    return notification


def mark_notification_read(notification: Notificacion) -> bool:
    if notification.leida_en is not None:
        return False

    notification.leida_en = utc_now()
    return True


def mark_notification_resolved(notification: Notificacion) -> bool:
    changed = False

    if notification.resuelta_en is None:
        notification.resuelta_en = utc_now()
        changed = True

    if notification.leida_en is None:
        notification.leida_en = notification.resuelta_en
        changed = True

    return changed


def resolve_notifications_for_entity(
    db: Session,
    *,
    entidad_tipo: str,
    entidad_id: int,
    tipo: str | None = None,
    destinatario_empleado_id: int | None = None,
) -> int:
    stmt = select(Notificacion).where(
        Notificacion.entidad_tipo == entidad_tipo,
        Notificacion.entidad_id == entidad_id,
        Notificacion.resuelta_en.is_(None),
    )

    if tipo:
        stmt = stmt.where(Notificacion.tipo == tipo)

    if destinatario_empleado_id is not None:
        stmt = stmt.where(
            Notificacion.destinatario_empleado_id == destinatario_empleado_id
        )

    notifications = list(db.execute(stmt).scalars().all())
    updated = 0

    for notification in notifications:
        if mark_notification_resolved(notification):
            updated += 1

    return updated
