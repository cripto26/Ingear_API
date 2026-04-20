from pydantic import BaseModel


class CuentaCobroBase(BaseModel):
    proyecto_id: int | None = None
    oportunidad_id: int | None = None
    cliente_id: int | None = None
    cliente_nombre: str | None = None
    nit: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    proyecto: str | None = None
    numero_contrato: str | None = None
    id_cotizacion: int | None = None


class CuentaCobroCreate(CuentaCobroBase):
    proyecto_id: int


class CuentaCobroUpdate(CuentaCobroBase):
    pass


class CuentaCobroPrefill(CuentaCobroBase):
    proyecto_id: int


class CuentaCobroOut(CuentaCobroBase):
    id: int

    class Config:
        from_attributes = True
