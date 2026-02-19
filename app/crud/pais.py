# app/crud/pais.py
from app.crud.base import CRUDBase
from app.models.pais import Pais

crud_pais = CRUDBase(Pais)
