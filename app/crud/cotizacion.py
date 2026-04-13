from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.cotizacion import Cotizacion
from app.models.cotizacion_version import CotizacionVersion


class CRUDCotizacion(CRUDBase[Cotizacion]):

    def _obtener_cotizacion_para_actualizar(
        self, db: Session, cotizacion_id: int
    ) -> Cotizacion | None:
        stmt = (
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.execute(stmt).scalar_one_or_none()


    def _obtener_siguiente_version(self, db: Session, cotizacion_id: int) -> int:
        stmt = select(
            func.coalesce(func.max(CotizacionVersion.versiones), 0)
        ).where(CotizacionVersion.cotizacion_id == cotizacion_id)
        return int(db.execute(stmt).scalar_one()) + 1


    def _construir_version_anterior(self, db_obj: Cotizacion, numero_version: int) -> dict:
        return {
            "cotizacion_id": db_obj.id,
            "id_empleado": db_obj.id_empleado,
            "id_oportunidad": db_obj.id_oportunidad,
            "url_cotizacion": db_obj.url_cotizacion,
            "tiempo_entrega": db_obj.tiempo_entrega,
            "nombre_cotizacion": db_obj.nombre_cotizacion,
            "tipo_cotizacion": db_obj.tipo_cotizacion,
            "etapa_cotizacion": db_obj.etapa_cotizacion,
            "forma_pago": db_obj.forma_pago,
            "tipo_servicio": db_obj.tipo_servicio,
            "estado": db_obj.estado,
            "sub_total": db_obj.sub_total,
            "total": db_obj.total,
            "productos": db_obj.productos,
            "versiones": numero_version,
        }

    def update(self, db: Session, db_obj: Cotizacion, obj_in: dict) -> Cotizacion:
        if not obj_in:
            return db_obj

        db_obj = self._obtener_cotizacion_para_actualizar(db, db_obj.id)
        if not db_obj:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

        cambios = {
            k: v for k, v in obj_in.items()
            if getattr(db_obj, k) != v
        }

        if not cambios:
            return db_obj

        try:
            numero_version = self._obtener_siguiente_version(db, db_obj.id)
            version_anterior = CotizacionVersion(
                **self._construir_version_anterior(db_obj, numero_version)
            )
            db.add(version_anterior)
            db.flush()

            for k, v in cambios.items():
                setattr(db_obj, k, v)

            db.commit()
            db.refresh(db_obj)
            return db_obj

        except IntegrityError as exc:
            db.rollback()
            diag = getattr(getattr(exc, "orig", None), "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)

            if constraint_name == "uq_cotizacion_versiones_cotizacion_version":
                raise HTTPException(
                    status_code=409,
                    detail="Conflicto de versionado: otra actualizacion genero la misma version al mismo tiempo. Intenta nuevamente.",
                ) from exc

            if constraint_name == "uq_cotizacion_versiones_v2_cotizacion_version":
                raise HTTPException(
                    status_code=409,
                    detail="Conflicto de versionado: otra actualizacion genero la misma version al mismo tiempo. Intenta nuevamente.",
                ) from exc



            if constraint_name in {
                "fk_cotizacion_versiones_proyecto",
                "fk_cotizacion_versiones_oportunidad",
            }:
                raise HTTPException(
                    status_code=409,
                    detail="La cotizacion referencia una oportunidad inexistente en el historial.",
                ) from exc


            raise HTTPException(
                status_code=409,
                detail=f"IntegrityError al actualizar cotizacion. Constraint: {constraint_name or 'desconocida'}",
            ) from exc


    def list_versions(self, db: Session, cotizacion_id: int):
        stmt = (
            select(CotizacionVersion)
            .where(CotizacionVersion.cotizacion_id == cotizacion_id)
            .order_by(CotizacionVersion.versiones.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def get_version(self, db: Session, cotizacion_id: int, numero_version: int):
        stmt = select(CotizacionVersion).where(
            CotizacionVersion.cotizacion_id == cotizacion_id,
            CotizacionVersion.versiones == numero_version,
        )
        return db.execute(stmt).scalar_one_or_none()
    
    


crud_cotizacion = CRUDCotizacion(Cotizacion)
