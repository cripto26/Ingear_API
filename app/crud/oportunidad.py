from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import MetaData, Table, delete, desc, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class CRUDOportunidad:
    table_name = "oportunidad"

    def _table(self, db: Session) -> Table:
        return Table(self.table_name, MetaData(), autoload_with=db.get_bind())

    def _clean_payload(self, table: Table, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_columns = {
            column.name for column in table.columns if not column.primary_key
        }
        return {key: value for key, value in payload.items() if key in allowed_columns}

    def get(self, db: Session, id: Any) -> Optional[dict[str, Any]]:
        table = self._table(db)
        stmt = select(table).where(table.c.id == id)
        row = db.execute(stmt).mappings().first()
        return dict(row) if row else None

    def list(self, db: Session, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        table = self._table(db)
        stmt = select(table).order_by(desc(table.c.id)).offset(skip).limit(limit)
        return [dict(row) for row in db.execute(stmt).mappings().all()]

    def create(self, db: Session, obj_in: dict[str, Any]) -> dict[str, Any]:
        table = self._table(db)
        payload = self._clean_payload(table, obj_in)
        stmt = insert(table).values(**payload).returning(table)
        try:
            row = db.execute(stmt).mappings().one()
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A resource with the same unique identifier already exists.",
            )
        return dict(row)

    def update(
        self,
        db: Session,
        db_obj: dict[str, Any],
        obj_in: dict[str, Any],
    ) -> dict[str, Any]:
        table = self._table(db)
        payload = self._clean_payload(table, obj_in)
        if not payload:
            return db_obj

        stmt = (
            update(table)
            .where(table.c.id == db_obj["id"])
            .values(**payload)
            .returning(table)
        )
        try:
            row = db.execute(stmt).mappings().one()
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="The update violates a unique constraint.",
            )
        return dict(row)

    def remove(self, db: Session, id: Any) -> Optional[dict[str, Any]]:
        obj = self.get(db, id)
        if not obj:
            return None

        table = self._table(db)
        try:
            db.execute(delete(table).where(table.c.id == id))
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "No se puede borrar la oportunidad porque tiene "
                    "cotizaciones, proyectos u otros datos relacionados."
                ),
            )
        return obj


crud_oportunidad = CRUDOportunidad()
