from pydantic import BaseModel


class CuentaCobroEditable(BaseModel):
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


class CuentaCobroWrite(BaseModel):
    proyecto_id: int | None = None
    oportunidad_id: int | None = None
    cliente_nombre: str | None = None
    nit: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    proyecto: str | None = None
    numero_contrato: str | None = None


class CuentaCobroCreate(CuentaCobroWrite):
    proyecto_id: int


class CuentaCobroUpdate(CuentaCobroWrite):
    pass


class CuentaCobroPrefill(CuentaCobroEditable):
    proyecto_id: int


class CuentaCobroOut(CuentaCobroEditable):
    id: int

    class Config:
        from_attributes = True
