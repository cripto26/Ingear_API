from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificacionOut(BaseModel):
    id: int
    destinatario_empleado_id: int
    actor_empleado_id: Optional[int] = None
    actor_nombre: Optional[str] = None
    tipo: str
    area: Optional[str] = None
    titulo: str
    mensaje: Optional[str] = None
    entidad_tipo: Optional[str] = None
    entidad_id: Optional[int] = None
    ruta_destino: Optional[str] = None
    requiere_accion: bool = False
    leida: bool = False
    resuelta: bool = False
    leida_en: Optional[datetime] = None
    resuelta_en: Optional[datetime] = None
    fecha_creacion: datetime


class NotificacionBatchOut(BaseModel):
    updated: int
