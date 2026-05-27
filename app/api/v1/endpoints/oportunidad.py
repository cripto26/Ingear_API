from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.db.session import get_db
from app.models.empleado import Empleado
from app.schemas.oportunidad import OportunidadCreate, OportunidadUpdate, OportunidadOut
from app.crud.oportunidad import crud_oportunidad
from app.services.oportunidad_totals import (
    apply_oportunidades_rubro_sin_iva,
    sync_oportunidad_rubro_sin_iva,
)

router = APIRouter()

opportunity_access = require_view_permissions("comercial.oportunidades")

@router.get("/", response_model=list[OportunidadOut])
def listar(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(opportunity_access),
):
    rows = crud_oportunidad.list(db, skip=skip, limit=limit)
    return apply_oportunidades_rubro_sin_iva(db, rows)

@router.get("/{oportunidad_id}", response_model=OportunidadOut)
def obtener(
    oportunidad_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(opportunity_access),
):
    obj = crud_oportunidad.get(db, oportunidad_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    apply_oportunidades_rubro_sin_iva(db, [obj])
    return obj

@router.post("/", response_model=OportunidadOut, status_code=201)
def crear(
    payload: OportunidadCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(opportunity_access),
):
    data = payload.model_dump()
    data.pop("rubro_sin_iva", None)

    oportunidad = crud_oportunidad.create(db, data)
    sync_oportunidad_rubro_sin_iva(db, oportunidad.id)
    db.commit()
    db.refresh(oportunidad)
    return oportunidad

@router.put("/{oportunidad_id}", response_model=OportunidadOut)
def actualizar(
    oportunidad_id: int,
    payload: OportunidadUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(opportunity_access),
):
    obj = crud_oportunidad.get(db, oportunidad_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")

    data = payload.model_dump(exclude_unset=True)
    data.pop("rubro_sin_iva", None)

    oportunidad = crud_oportunidad.update(db, obj, data)
    sync_oportunidad_rubro_sin_iva(db, oportunidad.id)
    db.commit()
    db.refresh(oportunidad)
    return oportunidad

@router.delete("/{oportunidad_id}", status_code=204)
def eliminar(
    oportunidad_id: int,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(opportunity_access),
):
    deleted = crud_oportunidad.remove(db, oportunidad_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return None
