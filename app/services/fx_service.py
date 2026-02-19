# app/services/fx_service.py

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
import xml.etree.ElementTree as ET

from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from app.schemas.fx import FxRatesOut, FxSources

# Intentar usar httpx si está instalado; si no, fallback a urllib (std lib)
try:
    import httpx  # type: ignore
    _HAS_HTTPX = True
except ModuleNotFoundError:
    httpx = None  # type: ignore
    _HAS_HTTPX = False


# Cache simple en memoria (TTL)
_CACHE: Dict[str, Tuple[float, FxRatesOut]] = {}
_CACHE_TTL_SECONDS = 30 * 60  # 30 min

# ---- Fuentes ----
# BanRep SDMX REST
BANREP_SDMX_BASE = "https://totoro.banrep.gov.co/nsi-jax-ws/rest/data"
BANREP_TRM_FLOWREF = "ESTAT,DF_TRM_DAILY_LATEST,1.0"  # TRM latest

# ECB: USD por 1 EUR (para calcular EUR/COP)
ECB_EXR_CSV_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/"
    "D.USD.EUR.SP00.A?lastNObservations=1&format=csvdata"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, val = hit
    if (time.time() - ts) <= _CACHE_TTL_SECONDS:
        return val
    return None


def _cache_set(key: str, val: FxRatesOut):
    _CACHE[key] = (time.time(), val)


def _normalize_date(date_str: str) -> str:
    """
    SDMX a veces retorna YYYY-MM-DD y a veces YYYYMMDD.
    Normalizamos a YYYY-MM-DD.
    """
    s = (date_str or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _parse_sdmx_generic_xml_for_last_obs(xml_bytes: bytes) -> Tuple[str, float]:
    """
    Parsea SDMX GenericData y extrae (fecha, valor) de la última observación válida.
    Busca:
      - ObsDimension value="YYYY-MM-DD" (o YYYYMMDD)
      - ObsValue value="1234.56"
    """
    root = ET.fromstring(xml_bytes)

    last_date = None
    last_value = None

    # Recorremos Observaciones
    for obs in root.iter():
        tag = obs.tag.split("}")[-1]  # quita namespace
        if tag != "Obs":
            continue

        obs_date = None
        obs_value = None

        for child in list(obs):
            ctag = child.tag.split("}")[-1]
            if ctag == "ObsDimension":
                obs_date = child.attrib.get("value")
            elif ctag == "ObsValue":
                v = child.attrib.get("value")
                if v is not None:
                    try:
                        obs_value = float(v)
                    except ValueError:
                        obs_value = None

        if obs_date and (obs_value is not None):
            last_date = obs_date
            last_value = obs_value

    if last_date is None or last_value is None:
        raise ValueError("No se encontró observación válida en respuesta SDMX.")

    return _normalize_date(last_date), last_value


def _parse_ecb_csv_for_last_obs(csv_text: str) -> Tuple[str, float]:
    """
    CSV del BCE: header + 1 fila.
    Necesitamos TIME_PERIOD y OBS_VALUE.
    """
    lines = [ln for ln in (csv_text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("CSV del BCE sin datos.")

    header = [h.strip().strip('"') for h in lines[0].split(",")]
    row = [c.strip().strip('"') for c in lines[-1].split(",")]

    def idx(name: str):
        try:
            return header.index(name)
        except ValueError:
            return -1

    i_time = idx("TIME_PERIOD")
    i_val = idx("OBS_VALUE")
    if i_time == -1 or i_val == -1:
        raise ValueError("CSV del BCE no contiene TIME_PERIOD/OBS_VALUE.")

    date = row[i_time]
    val = float(row[i_val])
    return date, val  # USD por 1 EUR


def _urllib_get(url: str, params: Optional[dict] = None, timeout: int = 20) -> Tuple[bytes, str]:
    """
    GET con stdlib. Retorna (bytes, text-decoded).
    """
    final_url = url
    if params:
        qs = urlencode(params)
        sep = "&" if "?" in url else "?"
        final_url = f"{url}{sep}{qs}"

    req = Request(
        final_url,
        headers={
            "User-Agent": "IngearAPI/1.0",
            "Accept": "*/*",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # Mejor esfuerzo para decodificar texto
            try:
                charset = resp.headers.get_content_charset() or "utf-8"
            except Exception:
                charset = "utf-8"
            text = data.decode(charset, errors="replace")
            return data, text
    except HTTPError as e:
        raise RuntimeError(f"HTTPError {e.code} en {final_url}") from e
    except URLError as e:
        raise RuntimeError(f"URLError en {final_url}: {e}") from e


async def _fetch_usd_cop_trm_banrep(client=None) -> Tuple[str, float]:
    url = f"{BANREP_SDMX_BASE}/{BANREP_TRM_FLOWREF}/all/ALL/"
    params = {"dimensionAtObservation": "TIME_PERIOD", "detail": "full"}

    if _HAS_HTTPX:
        assert client is not None, "httpx client requerido cuando httpx está disponible"
        r = await client.get(url, params=params, timeout=20)
        r.raise_for_status()
        return _parse_sdmx_generic_xml_for_last_obs(r.content)

    # Fallback stdlib
    data, _ = await asyncio.to_thread(_urllib_get, url, params, 20)
    return _parse_sdmx_generic_xml_for_last_obs(data)


async def _fetch_usd_per_eur_ecb(client=None) -> Tuple[str, float]:
    if _HAS_HTTPX:
        assert client is not None, "httpx client requerido cuando httpx está disponible"
        r = await client.get(ECB_EXR_CSV_URL, timeout=20)
        r.raise_for_status()
        return _parse_ecb_csv_for_last_obs(r.text)

    # Fallback stdlib
    _, text = await asyncio.to_thread(_urllib_get, ECB_EXR_CSV_URL, None, 20)
    return _parse_ecb_csv_for_last_obs(text)


async def get_fx_rates() -> FxRatesOut:
    cached = _cache_get("fx_rates")
    if cached:
        return cached

    if _HAS_HTTPX:
        async with httpx.AsyncClient() as client:  # type: ignore
            (trm_date, usd_cop), (eurusd_date, usd_per_eur) = await asyncio.gather(
                _fetch_usd_cop_trm_banrep(client),
                _fetch_usd_per_eur_ecb(client),
            )
    else:
        (trm_date, usd_cop), (eurusd_date, usd_per_eur) = await asyncio.gather(
            _fetch_usd_cop_trm_banrep(None),
            _fetch_usd_per_eur_ecb(None),
        )

    eur_cop = usd_cop * usd_per_eur

    out = FxRatesOut(
        usd_cop=round(usd_cop, 4),
        eur_cop=round(eur_cop, 4),
        trm_date=trm_date,
        eurusd_date=eurusd_date,
        fetched_at=_now_iso(),
        sources=FxSources(
            usd_cop="BanRep SDMX (DF_TRM_DAILY_LATEST)",
            usd_per_eur="ECB Data API (EXR D.USD.EUR.SP00.A)",
            note="EUR/COP calculado = (USD/COP TRM) * (USD por 1 EUR)",
        ),
    )

    _cache_set("fx_rates", out)
    return out
