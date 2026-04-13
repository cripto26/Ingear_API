from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_empleado
from app.db.session import get_db
from app.models.empleado import Empleado
from app.models.notificacion import Notificacion
from app.schemas.notificacion import NotificacionBatchOut, NotificacionOut
from app.services.notificacion_service import mark_notification_read

router = APIRouter()


def serialize_notification(notification: Notificacion) -> NotificacionOut:
    return NotificacionOut(
        id=notification.id,
        destinatario_empleado_id=notification.destinatario_empleado_id,
        actor_empleado_id=notification.actor_empleado_id,
        actor_nombre=notification.actor.nombre if notification.actor else None,
        tipo=notification.tipo,
        area=notification.area,
        titulo=notification.titulo,
        mensaje=notification.mensaje,
        entidad_tipo=notification.entidad_tipo,
        entidad_id=notification.entidad_id,
        ruta_destino=notification.ruta_destino,
        requiere_accion=notification.requiere_accion,
        leida=notification.leida_en is not None,
        resuelta=notification.resuelta_en is not None,
        leida_en=notification.leida_en,
        resuelta_en=notification.resuelta_en,
        fecha_creacion=notification.fecha_creacion,
    )


@router.get("/", response_model=list[NotificacionOut])
def listar(
    solo_no_leidas: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: Empleado = Depends(get_current_empleado),
):
    safe_limit = max(1, min(limit, 200))
    stmt = (
        select(Notificacion)
        .where(Notificacion.destinatario_empleado_id == current.id)
        .options(joinedload(Notificacion.actor))
        .order_by(desc(Notificacion.fecha_creacion))
        .limit(safe_limit)
    )

    if solo_no_leidas:
        stmt = stmt.where(Notificacion.leida_en.is_(None))

    rows = db.execute(stmt).scalars().all()
    return [serialize_notification(row) for row in rows]


@router.post("/{notificacion_id}/leer", response_model=NotificacionOut)
def marcar_como_leida(
    notificacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(get_current_empleado),
):
    notification = db.get(Notificacion, notificacion_id)
    if not notification or notification.destinatario_empleado_id != current.id:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")

    mark_notification_read(notification)
    db.commit()
    db.refresh(notification)
    return serialize_notification(notification)


@router.post("/marcar-todas-leidas", response_model=NotificacionBatchOut)
def marcar_todas_como_leidas(
    db: Session = Depends(get_db),
    current: Empleado = Depends(get_current_empleado),
):
    stmt = select(Notificacion).where(
        Notificacion.destinatario_empleado_id == current.id,
        Notificacion.leida_en.is_(None),
    )
    notifications = list(db.execute(stmt).scalars().all())

    updated = 0
    for notification in notifications:
        if mark_notification_read(notification):
            updated += 1

    db.commit()
    return NotificacionBatchOut(updated=updated)
