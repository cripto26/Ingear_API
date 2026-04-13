import json
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_empleado, require_view_permissions
from app.core.security import infer_role
from app.db.session import get_db
from app.models.cotizacion import Cotizacion
from app.models.empleado import Empleado
from app.models.producto import Producto
from app.schemas.cotizacion import (
    CotizacionCreate,
    CotizacionEmailIn,
    CotizacionEmailOut,
    CotizacionOut,
    CotizacionUpdate,
)
from app.crud.cotizacion import crud_cotizacion
from app.schemas.cotizacion_version import CotizacionVersionOut
from app.services.gmail_service import decode_pdf_base64, send_email_with_pdf
from app.services.notificacion_service import (
    create_notification,
    resolve_notifications_for_entity,
)


router = APIRouter()
cotizacion_access = require_view_permissions("comercial.cotizador")


def _serialize_productos(productos):
    if productos is None:
        return None
    return json.dumps(productos, ensure_ascii=False)


def _validar_productos_existentes(db: Session, productos) -> None:
    if not productos:
        return

    ids_producto = sorted({item["id_producto"] for item in productos})
    stmt = select(Producto.id).where(Producto.id.in_(ids_producto))
    ids_existentes = set(db.execute(stmt).scalars().all())
    ids_faltantes = [producto_id for producto_id in ids_producto if producto_id not in ids_existentes]

    if ids_faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Productos no encontrados: {ids_faltantes}",
        )


def _resolver_jefe_aprobador(db: Session, empleado: Empleado) -> Empleado | None:
    jefe_id = getattr(empleado, "jefe_id", None)
    if not jefe_id:
        return None

    jefe = db.get(Empleado, jefe_id)
    if not jefe:
        return None

    if (jefe.estado or "").strip().lower() != "activo":
        return None

    return jefe


def _build_cotizacion_aprobacion_message(
    actor: Empleado,
    cotizacion: Cotizacion,
) -> str:
    titulo = (cotizacion.nombre_cotizacion or "").strip()
    if titulo:
        return (
            f"{actor.nombre} creo la cotizacion \"{titulo}\" "
            "y requiere tu aprobacion."
        )

    return f"{actor.nombre} creo la cotizacion #{cotizacion.id} y requiere tu aprobacion."


@router.get("/", response_model=list[CotizacionOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    return crud_cotizacion.list(db, skip=skip, limit=limit)


@router.get("/{cotizacion_id}", response_model=CotizacionOut)
def obtener(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return obj


@router.post("/", response_model=CotizacionOut, status_code=201)
def crear(
    payload: CotizacionCreate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    data = payload.model_dump()
    _validar_productos_existentes(db, data["productos"])
    data["productos"] = _serialize_productos(data["productos"])
    data["id_empleado"] = current.id

    jefe_aprobador = _resolver_jefe_aprobador(db, current)
    data["estado"] = "1" if jefe_aprobador else "2"

    try:
        cotizacion = Cotizacion(**data)
        db.add(cotizacion)
        db.flush()

        if jefe_aprobador:
            create_notification(
                db,
                destinatario_empleado_id=jefe_aprobador.id,
                actor_empleado_id=current.id,
                tipo="cotizacion.aprobacion_requerida",
                area=current.area,
                titulo="Cotizacion pendiente de aprobacion",
                mensaje=_build_cotizacion_aprobacion_message(current, cotizacion),
                entidad_tipo="cotizacion",
                entidad_id=cotizacion.id,
                ruta_destino=f"/cotizador?cotizacionId={cotizacion.id}&approval=1",
                requiere_accion=True,
            )

        db.commit()
        db.refresh(cotizacion)
        return cotizacion
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No fue posible crear la cotizacion.",
        )


@router.put("/{cotizacion_id}", response_model=CotizacionOut)
def actualizar(
    cotizacion_id: int,
    payload: CotizacionUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    data = payload.model_dump(exclude_unset=True)
    if "productos" in data:
        _validar_productos_existentes(db, data["productos"])
        data["productos"] = _serialize_productos(data["productos"])

    return crud_cotizacion.update(db, obj, data)


@router.delete("/{cotizacion_id}", status_code=204)
def eliminar(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    deleted = crud_cotizacion.remove(db, cotizacion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return None


@router.post("/{cotizacion_id}/aprobar", response_model=CotizacionOut)
def aprobar(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(get_current_empleado),
):
    cotizacion = crud_cotizacion.get(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    jefe_id = getattr(cotizacion.empleado, "jefe_id", None)
    current_role = infer_role(current.area, current.cargo)
    can_approve = current.id == jefe_id or current_role == "GERENCIA"

    if not can_approve:
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para aprobar esta cotizacion.",
        )

    if (cotizacion.estado or "").strip() != "2":
        cotizacion.estado = "2"

    resolve_notifications_for_entity(
        db,
        entidad_tipo="cotizacion",
        entidad_id=cotizacion.id,
        tipo="cotizacion.aprobacion_requerida",
        destinatario_empleado_id=current.id if current.id == jefe_id else None,
    )
    db.commit()
    db.refresh(cotizacion)
    return cotizacion

@router.get("/{cotizacion_id}/versiones", response_model=list[CotizacionVersionOut])
def listar_versiones(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return crud_cotizacion.list_versions(db, cotizacion_id)


@router.get("/{cotizacion_id}/versiones/{numero_version}", response_model=CotizacionVersionOut)
def obtener_version(
    cotizacion_id: int,
    numero_version: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    version = crud_cotizacion.get_version(db, cotizacion_id, numero_version)
    if not version:
        raise HTTPException(status_code=404, detail="Version de cotizacion no encontrada")

    return version



def _clean_email(value: str | None, label: str) -> str:
    email = (value or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} no tiene un correo valido.",
        )
    return email


def _normalize_lookup(value: str | None) -> str:
    return (
        unicodedata.normalize("NFD", (value or "").strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _sanitize_filename_segment(value: str | None, fallback: str) -> str:
    cleaned = "".join(
        " " if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch
        for ch in (value or "")
    )
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned or fallback


def _service_label(value: str | None) -> str:
    normalized = _normalize_lookup(value)

    if not normalized:
        return ""
    if "ilumin" in normalized:
        return "ILUM"
    if "control" in normalized:
        return "CONTROL"
    if "instal" in normalized:
        return "INSTALACIÓN"
    if "manten" in normalized:
        return "MANTENIMIENTO"
    if "dise" in normalized:
        return "DISEÑO"

    return _sanitize_filename_segment(value.upper() if value else "", "GENERAL")


def _default_pdf_filename(cotizacion) -> str:
    service_label = _service_label(
        cotizacion.tipo_servicio or getattr(cotizacion.oportunidad, "tipo_servicio", None)
    )
    type_block = f"COT {service_label} INGEAR" if service_label else "COT INGEAR"
    project_name = _sanitize_filename_segment(
        getattr(cotizacion.oportunidad, "nombre_proyecto", None),
        "SIN NOMBRE DE PROYECTO",
    ).upper()
    client_name = _sanitize_filename_segment(
        getattr(getattr(cotizacion.oportunidad, "cliente", None), "razon_social", None),
        "SIN CLIENTE",
    ).upper()

    return f"{cotizacion.id} - {type_block} - {project_name} - {client_name}.pdf"


def _safe_pdf_filename(value: str | None, cotizacion) -> str:
    filename = (value or "").strip() or _default_pdf_filename(cotizacion)
    filename = filename.replace("\r", "").replace("\n", "")
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    return filename


def _default_subject(cotizacion_id: int, nombre_cotizacion: str | None) -> str:
    nombre = (nombre_cotizacion or "").strip()
    return f"Cotizacion IngeAr #{cotizacion_id}" if not nombre else f"IngeAr | {nombre}"


def _default_body(sender_name: str, sender_role: str | None, nombre_cotizacion: str | None) -> str:
    nombre = (nombre_cotizacion or "").strip() or "cotizacion solicitada"
    cargo = (sender_role or "").strip()
    firma = sender_name if not cargo else f"{sender_name}\n{cargo}"
    return (
        f"Hola,\n\n"
        f"Adjunto enviamos la {nombre} en formato PDF.\n\n"
        f"Quedamos atentos a cualquier comentario.\n\n"
        f"{firma}\n"
        f"IngeAr"
    )


@router.post("/{cotizacion_id}/enviar-email", response_model=CotizacionEmailOut)
def enviar_email_cotizacion(
    cotizacion_id: int,
    payload: CotizacionEmailIn,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    cotizacion = crud_cotizacion.get(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    if not cotizacion.oportunidad or not cotizacion.oportunidad.cliente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cotizacion no tiene cliente asociado.",
        )

    sender_email = _clean_email(current.email, "El empleado autenticado")
    to_email = _clean_email(
        payload.to_email or cotizacion.oportunidad.cliente.email,
        "El cliente asociado",
    )

    pdf_bytes = decode_pdf_base64(payload.pdf_base64)
    pdf_filename = _safe_pdf_filename(payload.pdf_filename, cotizacion)
    subject = (payload.subject or "").strip() or _default_subject(cotizacion.id, cotizacion.nombre_cotizacion)
    body = (payload.body or "").strip() or _default_body(current.nombre, current.cargo, cotizacion.nombre_cotizacion)

    gmail_message_id = send_email_with_pdf(
        sender_email=sender_email,
        sender_name=current.nombre,
        to_email=to_email,
        subject=subject,
        body=body,
        pdf_filename=pdf_filename,
        pdf_bytes=pdf_bytes,
    )

    return CotizacionEmailOut(
        message="Correo enviado correctamente",
        sender_email=sender_email,
        to_email=to_email,
        gmail_message_id=gmail_message_id,
    )
