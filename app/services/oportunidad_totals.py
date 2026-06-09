from collections.abc import MutableMapping
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.cotizacion import Cotizacion
from app.models.oportunidad import Oportunidad

OportunidadLike = Oportunidad | MutableMapping[str, Any]


def _get_oportunidad_id(oportunidad: OportunidadLike) -> int | None:
    raw_id = (
        oportunidad.get("id")
        if isinstance(oportunidad, MutableMapping)
        else getattr(oportunidad, "id", None)
    )
    if raw_id is None:
        return None

    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _set_oportunidad_rubro_sin_iva(
    oportunidad: OportunidadLike,
    total: Decimal,
) -> None:
    if isinstance(oportunidad, MutableMapping):
        oportunidad["rubro_sin_iva"] = total
        return

    set_committed_value(oportunidad, "rubro_sin_iva", total)


def calculate_oportunidad_rubro_sin_iva(
    db: Session,
    oportunidad_id: int | None,
) -> Decimal:
    if not oportunidad_id:
        return Decimal("0")

    value = db.execute(
        select(func.coalesce(func.sum(Cotizacion.sub_total), 0)).where(
            Cotizacion.id_oportunidad == oportunidad_id
        )
    ).scalar_one()

    return Decimal(str(value or 0))


def sync_oportunidad_rubro_sin_iva(
    db: Session,
    oportunidad_id: int | None,
) -> Oportunidad | None:
    if not oportunidad_id:
        return None

    oportunidad = db.get(Oportunidad, oportunidad_id)
    if not oportunidad:
        return None

    oportunidad.rubro_sin_iva = calculate_oportunidad_rubro_sin_iva(
        db,
        oportunidad_id,
    )
    return oportunidad


def apply_oportunidades_rubro_sin_iva(
    db: Session,
    oportunidades: list[OportunidadLike],
) -> list[OportunidadLike]:
    oportunidad_ids = [
        oportunidad_id
        for oportunidad in oportunidades
        if (oportunidad_id := _get_oportunidad_id(oportunidad)) is not None
    ]
    if not oportunidad_ids:
        return oportunidades

    totals = {
        int(oportunidad_id): Decimal(str(total or 0))
        for oportunidad_id, total in db.execute(
            select(
                Cotizacion.id_oportunidad,
                func.coalesce(func.sum(Cotizacion.sub_total), 0),
            )
            .where(Cotizacion.id_oportunidad.in_(oportunidad_ids))
            .group_by(Cotizacion.id_oportunidad)
        ).all()
    }

    for oportunidad in oportunidades:
        oportunidad_id = _get_oportunidad_id(oportunidad)
        if oportunidad_id is None:
            continue

        total = totals.get(oportunidad_id, Decimal("0"))
        _set_oportunidad_rubro_sin_iva(oportunidad, total)

    return oportunidades
