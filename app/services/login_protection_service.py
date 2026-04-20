import math
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass
class FailureState:
    timestamps: deque[float] = field(default_factory=deque)
    lock_until: float | None = None


def extract_client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def normalize_login_key(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


class LoginProtectionService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts_by_ip: dict[str, deque[float]] = {}
        self._attempts_by_user: dict[str, deque[float]] = {}
        self._failures_by_ip: dict[str, FailureState] = {}
        self._failures_by_user: dict[str, FailureState] = {}

    def assert_request_allowed(self, client_ip: str, login_key: str | None) -> None:
        now = time.time()

        with self._lock:
            lock_retry_after = max(
                self._get_lock_retry_after(self._failures_by_ip, client_ip, now),
                self._get_lock_retry_after(self._failures_by_user, login_key, now),
            )
            if lock_retry_after > 0:
                raise self._build_http_exception(
                    "Demasiados intentos fallidos. Espera antes de volver a intentar.",
                    lock_retry_after,
                )

            rate_retry_after = max(
                self._register_attempt_and_get_retry_after(
                    self._attempts_by_ip,
                    client_ip,
                    settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
                    settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS_PER_IP,
                    now,
                ),
                self._register_attempt_and_get_retry_after(
                    self._attempts_by_user,
                    login_key,
                    settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
                    settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS_PER_USER,
                    now,
                ),
            )
            if rate_retry_after > 0:
                raise self._build_http_exception(
                    "Demasiados intentos de inicio de sesion. Espera antes de volver a intentar.",
                    rate_retry_after,
                )

    def register_failure(
        self,
        client_ip: str,
        login_key: str | None,
        *,
        count_user: bool = True,
    ) -> None:
        now = time.time()

        with self._lock:
            self._record_failure(self._failures_by_ip, client_ip, now)
            if count_user:
                self._record_failure(self._failures_by_user, login_key, now)

    def register_success(self, client_ip: str, login_key: str | None) -> None:
        with self._lock:
            self._failures_by_ip.pop(client_ip, None)
            if login_key:
                self._failures_by_user.pop(login_key, None)

    def _record_failure(
        self,
        store: dict[str, FailureState],
        key: str | None,
        now: float,
    ) -> None:
        if not key:
            return

        state = store.setdefault(key, FailureState())
        self._prune_failures(state.timestamps, now)

        if state.lock_until and state.lock_until <= now:
            state.lock_until = None

        state.timestamps.append(now)

        if len(state.timestamps) < settings.LOGIN_FAILURE_LOCK_THRESHOLD:
            return

        overflow = len(state.timestamps) - settings.LOGIN_FAILURE_LOCK_THRESHOLD
        lock_seconds = min(
            settings.LOGIN_FAILURE_LOCK_BASE_SECONDS
            * (settings.LOGIN_FAILURE_LOCK_BACKOFF_MULTIPLIER ** overflow),
            settings.LOGIN_FAILURE_LOCK_MAX_SECONDS,
        )
        next_lock_until = now + lock_seconds
        state.lock_until = max(state.lock_until or 0, next_lock_until)

    def _get_lock_retry_after(
        self,
        store: dict[str, FailureState],
        key: str | None,
        now: float,
    ) -> int:
        if not key:
            return 0

        state = store.get(key)
        if not state:
            return 0

        self._prune_failures(state.timestamps, now)

        if state.lock_until and state.lock_until > now:
            return max(1, math.ceil(state.lock_until - now))

        state.lock_until = None
        if not state.timestamps:
            store.pop(key, None)
        return 0

    def _register_attempt_and_get_retry_after(
        self,
        store: dict[str, deque[float]],
        key: str | None,
        window_seconds: int,
        max_attempts: int,
        now: float,
    ) -> int:
        if not key or window_seconds <= 0 or max_attempts <= 0:
            return 0

        attempts = store.setdefault(key, deque())
        self._prune_attempts(attempts, now, window_seconds)
        attempts.append(now)

        if len(attempts) <= max_attempts:
            return 0

        retry_after = max(1, math.ceil(attempts[0] + window_seconds - now))
        return retry_after

    def _prune_attempts(
        self,
        attempts: deque[float],
        now: float,
        window_seconds: int,
    ) -> None:
        cutoff = now - window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def _prune_failures(self, attempts: deque[float], now: float) -> None:
        cutoff = now - settings.LOGIN_FAILURE_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def _build_http_exception(self, detail: str, retry_after: int) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{detail} Intenta de nuevo en {retry_after} segundos.",
            headers={"Retry-After": str(retry_after)},
        )


login_protection_service = LoginProtectionService()
