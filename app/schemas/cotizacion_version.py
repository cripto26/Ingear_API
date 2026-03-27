from datetime import datetime
from pydantic import ConfigDict

from app.schemas.cotizacion import CotizacionBase


class CotizacionVersionOut(CotizacionBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    cotizacion_id: int
    versiones: int
    fecha_creacion: datetime
