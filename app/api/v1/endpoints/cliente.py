from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteOut
from app.crud.cliente import crud_cliente

router = APIRouter()


@router.get("/", response_model=list[ClienteOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_cliente.list(db, skip=skip, limit=limit)


@router.get("/{cliente_id}", response_model=ClienteOut)
def obtener(cliente_id: int, db: Session = Depends(get_db)):
    obj = crud_cliente.get(db, cliente_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return obj


@router.post("/", response_model=ClienteOut, status_code=201)
def crear(payload: ClienteCreate, db: Session = Depends(get_db)):
    return crud_cliente.create(db, payload.model_dump())


@router.put("/{cliente_id}", response_model=ClienteOut)
def actualizar(cliente_id: int, payload: ClienteUpdate, db: Session = Depends(get_db)):
    obj = crud_cliente.get(db, cliente_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    data = payload.model_dump(exclude_unset=True)
    return crud_cliente.update(db, obj, data)


@router.delete("/{cliente_id}", status_code=204)
def eliminar(cliente_id: int, db: Session = Depends(get_db)):
    deleted = crud_cliente.remove(db, cliente_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return None
