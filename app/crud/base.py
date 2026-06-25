from typing import Any, Generic, Optional, Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy import String, desc, inspect, select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

ModelType = TypeVar("ModelType")


class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.get(self.model, id)

    def get_or_404(
        self,
        db: Session,
        id: Any,
        *,
        detail: str = "Registro no encontrado",
    ) -> ModelType:
        obj = self.get(db, id)
        if not obj:
            raise HTTPException(status_code=404, detail=detail)
        return obj

    def _resolve_list_ordering(self):
        if hasattr(self.model, "id"):
            return self.model.id, True

        primary_keys = inspect(self.model).primary_key
        if not primary_keys:
            return None, False

        primary_key = primary_keys[0]
        order_attr = getattr(self.model, primary_key.key, None)
        if order_attr is None:
            return None, False

        return order_attr, not isinstance(primary_key.type, String)

    def list(self, db: Session, skip: int = 0, limit: int = 50):
        stmt = select(self.model)
        order_attr, descending = self._resolve_list_ordering()
        if order_attr is not None:
            stmt = stmt.order_by(desc(order_attr) if descending else order_attr)
        stmt = stmt.offset(skip).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def create(self, db: Session, obj_in: dict) -> ModelType:
        obj = self.model(**obj_in)
        db.add(obj)
        try:
            db.commit()
            db.refresh(obj)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A resource with the same unique identifier already exists.",
            )
        return obj

    def update(self, db: Session, db_obj: ModelType, obj_in: dict) -> ModelType:
        for k, v in obj_in.items():
            setattr(db_obj, k, v)
        try:
            db.commit()
            db.refresh(db_obj)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="The update violates a unique constraint.",
            )
        return db_obj

    def remove(self, db: Session, id: Any) -> Optional[ModelType]:
        obj = self.get(db, id)
        if not obj:
            return None
        try:
            db.delete(obj)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "No se puede borrar el registro porque tiene datos "
                    "relacionados."
                ),
            )
        return obj

    def remove_or_404(
        self,
        db: Session,
        id: Any,
        *,
        detail: str = "Registro no encontrado",
    ) -> ModelType:
        obj = self.remove(db, id)
        if not obj:
            raise HTTPException(status_code=404, detail=detail)
        return obj
