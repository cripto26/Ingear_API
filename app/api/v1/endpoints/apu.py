from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_view_permissions
from app.crud.apu import crud_apu
from app.db.session import get_db
from app.models.apu import Apu
from app.models.empleado import Empleado
from app.models.producto import Producto
from app.schemas.apu import ApuCreate, ApuItem, ApuOut, ApuUpdate

router = APIRouter()
apu_access = require_view_permissions("comercial.productos")


def _normalize_tipo_producto(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="El tipo de producto es obligatorio.")
    return normalized.upper()


def _normalize_lookup(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_categoria(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return normalized.upper()


def _list_categoria_values(db: Session) -> list[str]:
    values: dict[str, str] = {}

    producto_rows = db.execute(
        select(Producto.categoria)
        .where(Producto.categoria.is_not(None))
        .where(func.length(func.trim(Producto.categoria)) > 0)
        .distinct()
    ).scalars()
    apu_rows = db.execute(
        select(Apu.categoria)
        .where(Apu.categoria.is_not(None))
        .where(func.length(func.trim(Apu.categoria)) > 0)
        .distinct()
    ).scalars()

    for value in [*producto_rows, *apu_rows]:
        clean = str(value or "").strip()
        key = _normalize_lookup(clean)
        if clean and key and key not in values:
            values[key] = clean

    return sorted(values.values(), key=_normalize_lookup)


def _canonical_categoria(db: Session, value: str | None) -> str | None:
    normalized = _normalize_categoria(value)
    if normalized is None:
        return None

    for categoria in _list_categoria_values(db):
        if _normalize_lookup(categoria) == normalized:
            return categoria

    return normalized


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


def _get_by_tipo_producto(db: Session, tipo_producto: str) -> Apu | None:
    return db.get(Apu, tipo_producto)


def _ensure_unique_tipo_producto(
    db: Session,
    tipo_producto: str,
    *,
    exclude_tipo_producto: str | None = None,
) -> None:
    normalized = _normalize_tipo_producto(tipo_producto)
    stmt = select(Apu.tipo_producto).where(
        func.upper(Apu.tipo_producto) == normalized
    )
    if exclude_tipo_producto is not None:
        stmt = stmt.where(Apu.tipo_producto != exclude_tipo_producto)

    existing = db.execute(stmt.limit(1)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un APU para el tipo de producto '{normalized}'.",
        )


@router.get("/categorias", response_model=list[str])
def listar_categorias(
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    return _list_categoria_values(db)


@router.get("/", response_model=list[ApuOut])
def listar(
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    stmt = select(Apu).order_by(Apu.tipo_producto)
    return list(db.execute(stmt).scalars().all())


@router.get("/{tipo_producto:path}", response_model=ApuOut)
def obtener(
    tipo_producto: str,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    obj = _get_by_tipo_producto(db, tipo_producto)
    if not obj:
        raise HTTPException(status_code=404, detail="APU no encontrado")
    return obj


@router.post("/", response_model=ApuOut, status_code=201)
def crear(
    payload: ApuCreate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    tipo_producto = _normalize_tipo_producto(payload.tipo_producto)
    _ensure_unique_tipo_producto(db, tipo_producto)

    data = {
        "tipo_producto": tipo_producto,
        "categoria": _canonical_categoria(db, payload.categoria),
        "items": _serialize_items(payload.items),
        "valor_total": _calculate_valor_total(payload.items),
    }
    return crud_apu.create(db, data)


@router.put("/{tipo_producto:path}", response_model=ApuOut)
def actualizar(
    tipo_producto: str,
    payload: ApuUpdate,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    obj = _get_by_tipo_producto(db, tipo_producto)
    if not obj:
        raise HTTPException(status_code=404, detail="APU no encontrado")

    next_tipo_producto = (
        _normalize_tipo_producto(payload.tipo_producto)
        if payload.tipo_producto is not None
        else obj.tipo_producto
    )

    if next_tipo_producto != obj.tipo_producto:
        _ensure_unique_tipo_producto(
            db,
            next_tipo_producto,
            exclude_tipo_producto=obj.tipo_producto,
        )

    next_items = payload.items
    data: dict[str, object] = {"tipo_producto": next_tipo_producto}

    if "categoria" in payload.model_fields_set:
        data["categoria"] = _canonical_categoria(db, payload.categoria)

    if next_items is not None:
        data["items"] = _serialize_items(next_items)
        data["valor_total"] = _calculate_valor_total(next_items)

    return crud_apu.update(db, obj, data)


@router.delete("/{tipo_producto:path}", status_code=204)
def eliminar(
    tipo_producto: str,
    db: Session = Depends(get_db),
    _current: Empleado = Depends(apu_access),
):
    deleted = crud_apu.remove(db, tipo_producto)
    if not deleted:
        raise HTTPException(status_code=404, detail="APU no encontrado")
    return None
