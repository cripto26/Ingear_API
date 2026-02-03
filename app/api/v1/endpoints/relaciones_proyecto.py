from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.proyecto import Proyecto
from app.models.empleado import Empleado
from app.models.cliente import Cliente
from app.models.despacho import Despacho

from app.models.proyecto_empleado import ProyectoEmpleado
from app.models.proyecto_cliente import ProyectoCliente
from app.models.proyecto_despacho import ProyectoDespacho

from app.schemas.proyecto_empleado import ProyectoEmpleadoLink
from app.schemas.proyecto_cliente import ProyectoClienteLink
from app.schemas.proyecto_despacho import ProyectoDespachoLink

router = APIRouter()


def _assert_exists(db: Session, model, obj_id: int, name: str):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"{name} no encontrado")
    return obj


# ---- EMPLEADOS EN PROYECTO ----
@router.post("/{proyecto_id}/empleados", status_code=201)
def asignar_empleado(proyecto_id: int, payload: ProyectoEmpleadoLink, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Empleado, payload.id_empleado, "Empleado")

    link = ProyectoEmpleado(id_proyecto=proyecto_id, id_empleado=payload.id_empleado)
    db.add(link)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relación proyecto-empleado ya existe")
    return {"ok": True}


@router.delete("/{proyecto_id}/empleados/{empleado_id}", status_code=204)
def quitar_empleado(proyecto_id: int, empleado_id: int, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Empleado, empleado_id, "Empleado")

    link = db.get(ProyectoEmpleado, {"id_proyecto": proyecto_id, "id_empleado": empleado_id})
    if not link:
        raise HTTPException(status_code=404, detail="Relación no encontrada")
    db.delete(link)
    db.commit()
    return None


# ---- CLIENTES EN PROYECTO ----
@router.post("/{proyecto_id}/clientes", status_code=201)
def asignar_cliente(proyecto_id: int, payload: ProyectoClienteLink, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Cliente, payload.id_cliente, "Cliente")

    link = ProyectoCliente(id_proyecto=proyecto_id, id_cliente=payload.id_cliente)
    db.add(link)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relación proyecto-cliente ya existe")
    return {"ok": True}


@router.delete("/{proyecto_id}/clientes/{cliente_id}", status_code=204)
def quitar_cliente(proyecto_id: int, cliente_id: int, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Cliente, cliente_id, "Cliente")

    link = db.get(ProyectoCliente, {"id_proyecto": proyecto_id, "id_cliente": cliente_id})
    if not link:
        raise HTTPException(status_code=404, detail="Relación no encontrada")
    db.delete(link)
    db.commit()
    return None


# ---- DESPACHOS EN PROYECTO ----
@router.post("/{proyecto_id}/despachos", status_code=201)
def asignar_despacho(proyecto_id: int, payload: ProyectoDespachoLink, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Despacho, payload.id_despacho, "Despacho")

    link = ProyectoDespacho(id_proyecto=proyecto_id, id_despacho=payload.id_despacho)
    db.add(link)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relación proyecto-despacho ya existe")
    return {"ok": True}


@router.delete("/{proyecto_id}/despachos/{despacho_id}", status_code=204)
def quitar_despacho(proyecto_id: int, despacho_id: int, db: Session = Depends(get_db)):
    _assert_exists(db, Proyecto, proyecto_id, "Proyecto")
    _assert_exists(db, Despacho, despacho_id, "Despacho")

    link = db.get(ProyectoDespacho, {"id_proyecto": proyecto_id, "id_despacho": despacho_id})
    if not link:
        raise HTTPException(status_code=404, detail="Relación no encontrada")
    db.delete(link)
    db.commit()
    return None
