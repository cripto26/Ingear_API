from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.empleado import Empleado
from app.core.security import hash_password

class CRUDEmpleado(CRUDBase[Empleado]):
    def get_by_login(self, db: Session, login: str):
        key = (login or "").strip().lower()
        stmt = select(Empleado).where(
            or_(func.lower(Empleado.email) == key, func.lower(Empleado.cedula) == key)
        )
        return db.execute(stmt).scalar_one_or_none()

    def create_secure(self, db: Session, obj_in: dict):
        obj_in["contrasena"] = hash_password(obj_in["contrasena"])
        return super().create(db, obj_in)

    def update_secure(self, db: Session, db_obj: Empleado, obj_in: dict):
        raw = obj_in.get("contrasena")
        if raw:
            obj_in["contrasena"] = hash_password(raw)
        elif "contrasena" in obj_in:
            obj_in.pop("contrasena")
        return super().update(db, db_obj, obj_in)

crud_empleado = CRUDEmpleado(Empleado)
