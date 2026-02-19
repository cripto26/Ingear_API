# app/api/v1/endpoints/fx.py
from fastapi import APIRouter, HTTPException

from app.schemas.fx import FxRatesOut
from app.services.fx_service import get_fx_rates

router = APIRouter()


@router.get("/rates", response_model=FxRatesOut)
async def read_fx_rates():
    """
    Devuelve:
    - usd_cop: TRM USD/COP (BanRep SDMX)
    - eur_cop: EUR/COP calculado = (usd_cop) * (usd por 1 eur del BCE)
    """
    try:
        return await get_fx_rates()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar TRM/EUR: {e}")
