from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.cotizacion import Cotizacion
from app.models.oportunidad import Oportunidad


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
    oportunidades: list[Oportunidad],
) -> list[Oportunidad]:
    oportunidad_ids = [
        int(oportunidad.id)
        for oportunidad in oportunidades
        if getattr(oportunidad, "id", None) is not None
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
        total = totals.get(int(oportunidad.id), Decimal("0"))
        set_committed_value(oportunidad, "rubro_sin_iva", total)

    return oportunidades
