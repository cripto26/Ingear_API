from pydantic import BaseModel, Field
from typing import Optional

class FxSources(BaseModel):
    usd_cop: str = Field(..., description="Fuente TRM USD/COP")
    usd_per_eur: str = Field(..., description="Fuente USD por 1 EUR")
    note: Optional[str] = Field(None, description="Aclaración de cálculo")

class FxRatesOut(BaseModel):
    usd_cop: float
    eur_cop: float
    trm_date: str
    eurusd_date: str
    fetched_at: str
    sources: FxSources
