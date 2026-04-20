import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


def validate_turnstile_token(
    token: str | None,
    remote_ip: str | None = None,
) -> None:
    if not settings.TURNSTILE_ENABLED:
        return

    if not settings.TURNSTILE_SECRET_KEY:
        logger.error("TURNSTILE_ENABLED=true pero TURNSTILE_SECRET_KEY no esta configurada.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La verificacion de seguridad no esta disponible.",
        )

    captcha_token = (token or "").strip()
    if not captcha_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completa la verificacion de seguridad.",
        )

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": captcha_token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        response = httpx.post(
            settings.TURNSTILE_SITEVERIFY_URL,
            data=payload,
            timeout=8.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPError as exc:
        logger.warning("No se pudo validar Turnstile contra Cloudflare: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo validar la verificacion de seguridad.",
        ) from exc
    except ValueError as exc:
        logger.warning("Turnstile respondio con un payload invalido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo validar la verificacion de seguridad.",
        ) from exc

    if result.get("success") is True:
        return

    logger.info(
        "Turnstile rechazo el login. error_codes=%s",
        result.get("error-codes"),
    )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="La verificacion de seguridad no fue valida.",
    )
