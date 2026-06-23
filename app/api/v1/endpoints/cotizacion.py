import json
import unicodedata
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_empleado, require_view_permissions
from app.core.security import infer_role
from app.db.session import get_db
from app.models.cotizacion import Cotizacion
from app.models.empleado import Empleado
from app.models.oportunidad import Oportunidad
from app.models.producto import Producto
from app.models.proyecto import Proyecto
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
from app.services.oportunidad_totals import sync_oportunidad_rubro_sin_iva


router = APIRouter()
cotizacion_access = require_view_permissions("comercial.cotizador")


def _normalize_team_lookup(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", (value or "").strip().lower())
    return "".join(char for char in raw if unicodedata.category(char) != "Mn")


def _is_management_employee(empleado: Empleado | None) -> bool:
    if empleado is None:
        return False
    return infer_role(empleado.area, empleado.cargo) == "GERENCIA"


def _looks_like_commercial_team_leader(empleado: Empleado | None) -> bool:
    if empleado is None:
        return False

    cargo = _normalize_team_lookup(empleado.cargo)
    if not cargo:
        return False

    return "lider" in cargo and "proyect" in cargo


def _build_team_anchor_by_empleado_id(empleados: list[Empleado]) -> dict[int, int]:
    direct_manager_ids = {
        int(empleado.jefe_id)
        for empleado in empleados
        if empleado.jefe_id is not None
    }
    team_anchor_by_id: dict[int, int] = {}

    for empleado in empleados:
        if _is_management_employee(empleado):
            team_anchor_by_id[empleado.id] = empleado.id
            continue

        

        if (
            _looks_like_commercial_team_leader(empleado)
            or empleado.id in direct_manager_ids
        ):
            team_anchor_by_id[empleado.id] = empleado.id
            continue

        if empleado.jefe_id is not None:
            team_anchor_by_id[empleado.id] = int(empleado.jefe_id)
            continue

        team_anchor_by_id[empleado.id] = empleado.id

    return team_anchor_by_id


def _load_empleado_directory(
    db: Session,
) -> tuple[dict[int, Empleado], dict[int, int]]:
    empleados = list(db.execute(select(Empleado)).scalars().all())
    empleados_by_id = {empleado.id: empleado for empleado in empleados}
    team_anchor_by_id = _build_team_anchor_by_empleado_id(empleados)
    return empleados_by_id, team_anchor_by_id


def _can_edit_cotizacion(
    current: Empleado,
    owner: Empleado | None,
    team_anchor_by_id: dict[int, int],
) -> bool:
    if _is_management_employee(current):
        return True

    if owner is None:
        return False

    if current.id == owner.id:
        return True

    current_anchor = team_anchor_by_id.get(current.id, current.id)
    owner_anchor = team_anchor_by_id.get(owner.id, owner.id)
    return current_anchor == owner_anchor


def _annotate_cotizacion_permissions(
    db: Session,
    current: Empleado,
    cotizaciones: Cotizacion | list[Cotizacion],
):
    rows = cotizaciones if isinstance(cotizaciones, list) else [cotizaciones]

    if _is_management_employee(current):
        for row in rows:
            setattr(row, "can_edit", True)
            setattr(row, "can_duplicate", True)
        return cotizaciones

    if all(current.id == row.id_empleado for row in rows):
        for row in rows:
            setattr(row, "can_edit", True)
            setattr(row, "can_duplicate", True)
        return cotizaciones

    empleados_by_id, team_anchor_by_id = _load_empleado_directory(db)
    empleados_by_id.setdefault(current.id, current)

    for row in rows:
        owner = empleados_by_id.get(row.id_empleado)
        setattr(
            row,
            "can_edit",
            _can_edit_cotizacion(current, owner, team_anchor_by_id),
        )
        setattr(row, "can_duplicate", True)

    return cotizaciones


def _assert_can_edit_cotizacion(
    db: Session,
    current: Empleado,
    cotizacion: Cotizacion,
) -> None:
    if _is_management_employee(current) or current.id == cotizacion.id_empleado:
        return

    empleados_by_id, team_anchor_by_id = _load_empleado_directory(db)
    empleados_by_id.setdefault(current.id, current)
    owner = empleados_by_id.get(cotizacion.id_empleado)

    if _can_edit_cotizacion(current, owner, team_anchor_by_id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "No tienes permisos para editar esta cotizacion. Solo puedes "
            "editar cotizaciones de tu equipo comercial. Si pertenece a otro "
            "equipo, debes duplicarla."
        ),
    )


def _normalize_stage(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", (value or "").strip().lower())
    return "".join(char for char in raw if unicodedata.category(char) != "Mn")


def _is_won_stage(value: str | None) -> bool:
    return _normalize_stage(value) == "ganada"


def _normalize_extension(value: str | None, fallback: str = "pdf") -> str:
    cleaned = "".join(
        char for char in str(value or fallback).lower() if char.isalnum()
    )
    return cleaned or fallback


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


def _productos_tienen_costo_fabrica_override(productos) -> bool:
    if not productos:
        return False

    return any(
        item.get("costo_fabrica_override") is not None for item in productos
    )


def _build_productos_override_fingerprint(productos) -> list[tuple[int, int, float]]:
    if not productos:
        return []

    fingerprint: list[tuple[int, int, float]] = []
    for item in productos:
        override = item.get("costo_fabrica_override")
        if override is None:
            continue

        fingerprint.append(
            (
                int(item.get("id_producto") or 0),
                int(item.get("particion") or 0),
                float(override),
            )
        )

    return sorted(fingerprint)


def _load_serialized_productos(value) -> list[dict]:
    if value is None or value == "":
        return []

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    return value if isinstance(value, list) else []


def _validar_permiso_costo_fabrica_override_creacion(
    current: Empleado,
    productos,
) -> None:
    if not _productos_tienen_costo_fabrica_override(productos):
        return

    current_role = infer_role(current.area, current.cargo)
    if current_role == "GERENCIA":
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Solo gerencia puede modificar el costo fabrica a nivel de "
            "cotizacion."
        ),
    )


def _validar_permiso_costo_fabrica_override_actualizacion(
    current: Empleado,
    productos_nuevos,
    productos_actuales,
) -> None:
    if not _productos_tienen_costo_fabrica_override(productos_nuevos):
        return

    current_role = infer_role(current.area, current.cargo)
    if current_role == "GERENCIA":
        return

    current_fingerprint = Counter(
        _build_productos_override_fingerprint(productos_actuales)
    )
    next_fingerprint = Counter(
        _build_productos_override_fingerprint(productos_nuevos)
    )

    if not (next_fingerprint - current_fingerprint):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Solo gerencia puede modificar el costo fabrica a nivel de "
            "cotizacion."
        ),
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


def _build_quote_document_base_name(
    cotizacion_id: int | None,
    tipo_servicio: str | None,
    nombre_proyecto: str | None,
    cliente_nombre: str | None,
) -> str:
    service_label = _service_label(tipo_servicio)
    type_block = f"COT {service_label} INGEAR" if service_label else "COT INGEAR"
    project_name = _sanitize_filename_segment(
        nombre_proyecto,
        "SIN NOMBRE DE PROYECTO",
    ).upper()
    client_name = _sanitize_filename_segment(cliente_nombre, "SIN CLIENTE").upper()
    id_label = _sanitize_filename_segment(
        str(cotizacion_id) if cotizacion_id else None,
        "PENDIENTE",
    )

    return f"{id_label} - {type_block} - {project_name} - {client_name}"


def _build_quote_document_filename(
    cotizacion_id: int | None,
    tipo_servicio: str | None,
    nombre_proyecto: str | None,
    cliente_nombre: str | None,
    extension: str | None = "pdf",
) -> str:
    base_name = _build_quote_document_base_name(
        cotizacion_id=cotizacion_id,
        tipo_servicio=tipo_servicio,
        nombre_proyecto=nombre_proyecto,
        cliente_nombre=cliente_nombre,
    )
    safe_extension = _normalize_extension(extension)
    return f"{base_name}.{safe_extension}"


def _build_oportunidad_cotizaciones_value(
    cotizacion: Cotizacion,
    oportunidad: Oportunidad | None,
) -> str:
    cliente_nombre = getattr(getattr(oportunidad, "cliente", None), "razon_social", None)

    return _build_quote_document_filename(
        cotizacion_id=cotizacion.id,
        tipo_servicio=cotizacion.tipo_servicio or getattr(oportunidad, "tipo_servicio", None),
        nombre_proyecto=getattr(oportunidad, "nombre_proyecto", None),
        cliente_nombre=cliente_nombre,
        extension="xlsx",
    )


def _split_cotizaciones_entries(value: str | None) -> list[str]:
    seen: set[str] = set()
    entries: list[str] = []

    normalized_text = str(value or "").replace("\r", "\n")
    for raw_entry in normalized_text.split("\n"):
        entry = raw_entry.strip()
        if not entry or entry in seen:
            continue
        seen.add(entry)
        entries.append(entry)

    return entries


def _join_cotizaciones_entries(entries: list[str]) -> str | None:
    clean_entries = [entry.strip() for entry in entries if entry and entry.strip()]
    return "\n".join(clean_entries) if clean_entries else None


def _upsert_cotizaciones_value(
    current_text: str | None,
    next_entry: str,
    *,
    previous_entry: str | None = None,
) -> str:
    normalized_previous = (previous_entry or "").strip()
    normalized_next = next_entry.strip()
    base_entries: list[str] = []

    for entry in _split_cotizaciones_entries(current_text):
        if normalized_previous and entry == normalized_previous:
            continue
        if entry == normalized_next:
            continue
        base_entries.append(entry)

    base_entries.append(normalized_next)
    return _join_cotizaciones_entries(base_entries) or normalized_next


def _remove_cotizaciones_entry(
    current_text: str | None,
    entry_to_remove: str | None,
) -> str | None:
    normalized_remove = (entry_to_remove or "").strip()
    if not normalized_remove:
        return _join_cotizaciones_entries(_split_cotizaciones_entries(current_text))

    filtered_entries = [
        entry
        for entry in _split_cotizaciones_entries(current_text)
        if entry != normalized_remove
    ]
    return _join_cotizaciones_entries(filtered_entries)


def _find_existing_proyecto_for_oportunidad(
    db: Session,
    oportunidad_id: int,
) -> Proyecto | None:
    stmt = (
        select(Proyecto)
        .where(Proyecto.oportunidad_id == oportunidad_id)
        .order_by(Proyecto.id.asc())
    )
    return db.execute(stmt).scalars().first()


def _sync_oportunidad_cotizaciones(
    db: Session,
    cotizacion: Cotizacion,
    *,
    fecha_probable_venta: date | None = None,
    previous_oportunidad_id: int | None = None,
    previous_cotizaciones_value: str | None = None,
) -> Oportunidad:
    oportunidad_id = cotizacion.id_oportunidad
    if not oportunidad_id:
        raise HTTPException(
            status_code=400,
            detail="La cotizacion debe estar ligada a una oportunidad.",
        )

    oportunidad = db.get(Oportunidad, oportunidad_id)
    if not oportunidad:
        raise HTTPException(
            status_code=400,
            detail="La oportunidad asociada a la cotizacion no existe.",
        )

    next_cotizacion_value = _build_oportunidad_cotizaciones_value(
        cotizacion,
        oportunidad,
    )
    same_oportunidad = previous_oportunidad_id == oportunidad_id
    oportunidad.cotizaciones = _upsert_cotizaciones_value(
        oportunidad.cotizaciones,
        next_cotizacion_value,
        previous_entry=previous_cotizaciones_value if same_oportunidad else None,
    )

    fecha_envio = (
        cotizacion.fecha_creacion.date()
        if getattr(cotizacion, "fecha_creacion", None) is not None
        else date.today()
    )

    if oportunidad.fecha_cotizacion is None:
        oportunidad.fecha_cotizacion = fecha_envio

    if oportunidad.fecha_cierre is None and fecha_probable_venta is not None:
        oportunidad.fecha_cierre = fecha_probable_venta

    sync_oportunidad_rubro_sin_iva(db, oportunidad_id)

    if previous_oportunidad_id and previous_oportunidad_id != oportunidad_id:
        oportunidad_anterior = db.get(Oportunidad, previous_oportunidad_id)
        if oportunidad_anterior:
            oportunidad_anterior.cotizaciones = _remove_cotizaciones_entry(
                oportunidad_anterior.cotizaciones,
                previous_cotizaciones_value,
            )
            sync_oportunidad_rubro_sin_iva(db, previous_oportunidad_id)

    return oportunidad


@router.get("/", response_model=list[CotizacionOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    rows = crud_cotizacion.list(db, skip=skip, limit=limit)
    return _annotate_cotizacion_permissions(db, current, rows)


@router.get("/{cotizacion_id}", response_model=CotizacionOut)
def obtener(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return _annotate_cotizacion_permissions(db, current, obj)


@router.post("/", response_model=CotizacionOut, status_code=201)
def crear(
    payload: CotizacionCreate,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    data = payload.model_dump()
    fecha_probable_venta = data.pop("fecha_probable_venta", None)
    _validar_permiso_costo_fabrica_override_creacion(current, data["productos"])
    _validar_productos_existentes(db, data["productos"])
    data["productos"] = _serialize_productos(data["productos"])
    data["id_empleado"] = current.id

    jefe_aprobador = _resolver_jefe_aprobador(db, current)
    data["estado"] = "1" if jefe_aprobador else "2"

    try:
        cotizacion = Cotizacion(**data)
        db.add(cotizacion)
        db.flush()
        _sync_oportunidad_cotizaciones(
            db,
            cotizacion,
            fecha_probable_venta=fecha_probable_venta,
        )

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
        setattr(cotizacion, "can_edit", True)
        setattr(cotizacion, "can_duplicate", True)
        return cotizacion
    except HTTPException:
        db.rollback()
        raise
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
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    _assert_can_edit_cotizacion(db, current, obj)

    data = payload.model_dump(exclude_unset=True)
    # El propietario/asesor de una cotizacion no debe cambiar por editarla
    # desde otra cuenta con permisos.
    data.pop("id_empleado", None)
    fecha_probable_venta = data.pop("fecha_probable_venta", None)
    crear_proyecto_ganada = bool(data.pop("crear_proyecto_ganada", False))
    if "productos" in data:
        _validar_permiso_costo_fabrica_override_actualizacion(
            current,
            data["productos"],
            _load_serialized_productos(obj.productos),
        )
        _validar_productos_existentes(db, data["productos"])
        data["productos"] = _serialize_productos(data["productos"])

    oportunidad_anterior_id = obj.id_oportunidad
    oportunidad_anterior = (
        db.get(Oportunidad, oportunidad_anterior_id)
        if oportunidad_anterior_id
        else None
    )
    cotizacion_anterior_en_oportunidad = (
        _build_oportunidad_cotizaciones_value(obj, oportunidad_anterior)
        if oportunidad_anterior
        else None
    )
    etapa_anterior = obj.etapa_cotizacion
    etapa_siguiente = data.get("etapa_cotizacion", obj.etapa_cotizacion)

    if crear_proyecto_ganada and (
        _is_won_stage(etapa_anterior) or not _is_won_stage(etapa_siguiente)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Solo se puede crear un proyecto cuando la etapa de la "
                "cotizacion cambia a Ganada."
            ),
        )

    proyecto = None
    proyecto_creado_id = None

    try:
        obj = crud_cotizacion.update(db, obj, data, commit=False)

        if crear_proyecto_ganada:
            oportunidad_id = obj.id_oportunidad
            if not oportunidad_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "La cotizacion debe estar ligada a una oportunidad para "
                        "crear el proyecto."
                    ),
                )

            oportunidad = db.get(Oportunidad, oportunidad_id)
            if not oportunidad:
                raise HTTPException(
                    status_code=400,
                    detail="La oportunidad asociada a la cotizacion no existe.",
                )

            proyecto_existente = _find_existing_proyecto_for_oportunidad(
                db,
                oportunidad.id,
            )
            if proyecto_existente is None:
                nombre_proyecto = (oportunidad.nombre_proyecto or "").strip()
                if not nombre_proyecto:
                    raise HTTPException(
                        status_code=400,
                        detail="La oportunidad asociada no tiene nombre de proyecto.",
                    )

                proyecto = Proyecto(
                    nombre=nombre_proyecto,
                    oportunidad_id=oportunidad.id,
                )
                db.add(proyecto)

        _sync_oportunidad_cotizaciones(
            db,
            obj,
            fecha_probable_venta=fecha_probable_venta,
            previous_oportunidad_id=oportunidad_anterior_id,
            previous_cotizaciones_value=cotizacion_anterior_en_oportunidad,
        )

        db.commit()
        db.refresh(obj)
        if proyecto is not None:
            db.refresh(proyecto)
            proyecto_creado_id = proyecto.id
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible actualizar la cotizacion.",
        )

    setattr(obj, "proyecto_creado_id", proyecto_creado_id)
    setattr(obj, "can_edit", True)
    setattr(obj, "can_duplicate", True)
    return obj


@router.delete("/{cotizacion_id}", status_code=204)
def eliminar(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    current: Empleado = Depends(cotizacion_access),
):
    obj = crud_cotizacion.get(db, cotizacion_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    _assert_can_edit_cotizacion(db, current, obj)

    oportunidad_id = obj.id_oportunidad
    oportunidad = db.get(Oportunidad, oportunidad_id) if oportunidad_id else None
    cotizacion_en_oportunidad = (
        _build_oportunidad_cotizaciones_value(obj, oportunidad)
        if oportunidad
        else None
    )

    try:
        db.delete(obj)
        if oportunidad:
            oportunidad.cotizaciones = _remove_cotizaciones_entry(
                oportunidad.cotizaciones,
                cotizacion_en_oportunidad,
            )
        db.flush()
        sync_oportunidad_rubro_sin_iva(db, oportunidad_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible eliminar la cotizacion.",
        )

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
    setattr(cotizacion, "can_edit", True)
    setattr(cotizacion, "can_duplicate", True)
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
    return _build_quote_document_filename(
        cotizacion_id=cotizacion.id,
        tipo_servicio=(
            cotizacion.tipo_servicio
            or getattr(cotizacion.oportunidad, "tipo_servicio", None)
        ),
        nombre_proyecto=getattr(cotizacion.oportunidad, "nombre_proyecto", None),
        cliente_nombre=getattr(
            getattr(cotizacion.oportunidad, "cliente", None),
            "razon_social",
            None,
        ),
        extension="pdf",
    )


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
