from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Ingear API"
    DATABASE_URL: str
    GOOGLE_SERVICE_ACCOUNT_FILE: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_HOURS: int = 8
    REFRESH_COOKIE_NAME: str = "ingear_refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    REFRESH_COOKIE_DOMAIN: Optional[str] = None
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_SECRET_KEY: Optional[str] = None
    TURNSTILE_SITEVERIFY_URL: str = (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    WORLD_OFFICE_ENABLED: bool = False
    WORLD_OFFICE_SERVER: Optional[str] = None
    WORLD_OFFICE_DATABASE: str = "WData"
    WORLD_OFFICE_USERNAME: Optional[str] = None
    WORLD_OFFICE_PASSWORD: Optional[str] = None
    WORLD_OFFICE_ODBC_DRIVER: str = "SQL Server"
    WORLD_OFFICE_CONNECTION_TIMEOUT_SECONDS: int = 5
    WORLD_OFFICE_QUERY_TIMEOUT_SECONDS: int = 20
    WORLD_OFFICE_INVENTORY_CACHE_SECONDS: int = 300
    WORLD_OFFICE_BODEGA_CODIGO: Optional[str] = None
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS_PER_IP: int = 20
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS_PER_USER: int = 10
    LOGIN_FAILURE_WINDOW_SECONDS: int = 900
    LOGIN_FAILURE_LOCK_THRESHOLD: int = 5
    LOGIN_FAILURE_LOCK_BASE_SECONDS: int = 60
    LOGIN_FAILURE_LOCK_BACKOFF_MULTIPLIER: int = 2
    LOGIN_FAILURE_LOCK_MAX_SECONDS: int = 900



settings = Settings()
