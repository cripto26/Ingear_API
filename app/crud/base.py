from typing import Any, Generic, Optional, Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

ModelType = TypeVar("ModelType")


class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.get(self.model, id)

    def list(self, db: Session, skip: int = 0, limit: int = 50):
        stmt = select(self.model).offset(skip).limit(limit)
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
        db.delete(obj)
        db.commit()
        return obj
