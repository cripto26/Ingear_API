# app/api/v1/endpoints/pais.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.crud.pais import crud_pais
from app.schemas.pais import PaisCreate, PaisOut, PaisUpdate

router = APIRouter()


@router.get("/", response_model=list[PaisOut])
def listar(skip: int = 0, limit: int = 1000, db: Session = Depends(get_db)):
    return crud_pais.list(db, skip=skip, limit=limit)


@router.get("/{pais}", response_model=PaisOut)
def obtener(pais: str, db: Session = Depends(get_db)):
    obj = crud_pais.get(db, pais)
    if not obj:
        raise HTTPException(status_code=404, detail="Pais no encontrado")
    return obj


@router.post("/", response_model=PaisOut, status_code=201)
def crear(payload: PaisCreate, db: Session = Depends(get_db)):
    # evita duplicados por PK
    existing = crud_pais.get(db, payload.pais)
    if existing:
        raise HTTPException(status_code=409, detail="Ese pais ya existe")

    # Pydantic v2 -> model_dump()
    return crud_pais.create(db, payload.model_dump())


@router.put("/{pais}", response_model=PaisOut)
def actualizar(pais: str, payload: PaisUpdate, db: Session = Depends(get_db)):
    obj = crud_pais.get(db, pais)
    if not obj:
        raise HTTPException(status_code=404, detail="Pais no encontrado")

    data = payload.model_dump(exclude_unset=True)
    return crud_pais.update(db, obj, data)


@router.delete("/{pais}", status_code=204)
def eliminar(pais: str, db: Session = Depends(get_db)):
    deleted = crud_pais.remove(db, pais)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pais no encontrado")
    return None
