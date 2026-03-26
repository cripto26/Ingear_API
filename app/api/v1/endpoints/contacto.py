from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contacto import ContactoCreate, ContactoUpdate, ContactoOut
from app.crud.contacto import crud_contacto

router = APIRouter()


@router.get("/", response_model=list[ContactoOut])
def listar(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return crud_contacto.list(db, skip=skip, limit=limit)


@router.get("/{contacto_id}", response_model=ContactoOut)
def obtener(contacto_id: int, db: Session = Depends(get_db)):
    obj = crud_contacto.get(db, contacto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return obj


@router.post("/", response_model=ContactoOut, status_code=201)
def crear(payload: ContactoCreate, db: Session = Depends(get_db)):
    return crud_contacto.create(db, payload.model_dump())


@router.put("/{contacto_id}", response_model=ContactoOut)
def actualizar(contacto_id: int, payload: ContactoUpdate, db: Session = Depends(get_db)):
    obj = crud_contacto.get(db, contacto_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return crud_contacto.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{contacto_id}", status_code=204)
def eliminar(contacto_id: int, db: Session = Depends(get_db)):
    deleted = crud_contacto.remove(db, contacto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return None
