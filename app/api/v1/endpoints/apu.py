from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.crud.apu import crud_apu
from app.db.session import get_db
from app.models.apu import Apu
from app.models.empleado import Empleado
from app.schemas.apu import ApuCreate, ApuItem, ApuOut, ApuUpdate

router = APIRouter()
apu_access = require_view_permissions("comercial.productos")


def _normalize_subtipo(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="El subtipo es obligatorio.")
    return normalized.upper()


def _serialize_items(items: list[ApuItem]) -> list[list[object]]:
    return [
        [
            item.item.strip().upper(),
            float(item.qty),
            float(item.valor_unitario),
        ]
        for item in items
    ]


def _calculate_valor_total(items: list[ApuItem]) -> Decimal:
    total = sum(
        (item.qty * item.valor_unitario for item in items),
        start=Decimal("0"),
    )
    return total.quantize(Decimal("0.01"))


def _get_by_subtipo(db: Session, subtipo: str) -> Apu | None:
    return db.get(Apu, subtipo)


def _ensure_unique_subtipo(
    db: Session,
    subtipo: str,
    *,
    exclude_subtipo: str | None = None,
) -> None:
    normalized = _normalize_subtipo(subtipo)
    stmt = select(Apu.subtipo).where(func.upper(Apu.subtipo) == normalized)
    if exclude_subtipo is not None:
        stmt = stmt.where(Apu.subtipo != exclude_subtipo)

    existing = db.execute(stmt.limit(1)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un APU para el subtipo '{normalized}'.",
        )


@router.get("/", response_model=list[ApuOut])
def listar(
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    stmt = select(Apu).order_by(Apu.subtipo)
    return list(db.execute(stmt).scalars().all())


@router.get("/{subtipo:path}", response_model=ApuOut)
def obtener(
    subtipo: str,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    obj = _get_by_subtipo(db, subtipo)
    if not obj:
        raise HTTPException(status_code=404, detail="APU no encontrado")
    return obj


@router.post("/", response_model=ApuOut, status_code=201)
def crear(
    payload: ApuCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    subtipo = _normalize_subtipo(payload.subtipo)
    _ensure_unique_subtipo(db, subtipo)

    data = {
        "subtipo": subtipo,
        "items": _serialize_items(payload.items),
        "valor_total": _calculate_valor_total(payload.items),
    }
    return crud_apu.create(db, data)


@router.put("/{subtipo:path}", response_model=ApuOut)
def actualizar(
    subtipo: str,
    payload: ApuUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    obj = _get_by_subtipo(db, subtipo)
    if not obj:
        raise HTTPException(status_code=404, detail="APU no encontrado")

    next_subtipo = (
        _normalize_subtipo(payload.subtipo)
        if payload.subtipo is not None
        else obj.subtipo
    )

    if next_subtipo != obj.subtipo:
        _ensure_unique_subtipo(db, next_subtipo, exclude_subtipo=obj.subtipo)

    next_items = payload.items
    data: dict[str, object] = {"subtipo": next_subtipo}

    if next_items is not None:
        data["items"] = _serialize_items(next_items)
        data["valor_total"] = _calculate_valor_total(next_items)

    return crud_apu.update(db, obj, data)


@router.delete("/{subtipo:path}", status_code=204)
def eliminar(
    subtipo: str,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    deleted = crud_apu.remove(db, subtipo)
    if not deleted:
        raise HTTPException(status_code=404, detail="APU no encontrado")
    return None
