"""HTTP client for the Aurum REST API.

A thin wrapper over httpx — the single place that knows the base URL,
optional basic auth, and the error shape the backend returns. The
idempotency rule lives here: only GET is retried on transport errors.
A timed-out POST might have already been applied, so writes fail loudly
instead of silently doubling a transaction.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import AgentConfig

# Transport-level retries for read-only requests. Writes get none.
GET_RETRIES = 2
# Backoff between GET retries; read at call time so tests can zero it out.
RETRY_BACKOFF_SECONDS = 0.3
# Applied once at client construction (standard httpx usage); unlike the
# backoff above it is not something tests need to patch.
REQUEST_TIMEOUT = httpx.Timeout(15.0)

# Endpoints the client itself talks to (the tools keep their own PATH_*
# constants in tools.py). /health sits behind no auth and backs the
# Docker healthcheck; /settings carries the display currency.
HEALTH_PATH = "/health"
SETTINGS_PATH = "/settings"


class AurumApiError(Exception):
    """API call failed. Carries the HTTP status (0 for transport errors).

    The message is fed back to the model as a tool result, so it contains
    the backend's own error text — enough for the model to self-correct.
    """

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


def format_error_detail(payload: Any) -> str:
    """Pull a readable message out of a FastAPI error body.

    Business errors (400/404) carry ``{"detail": "string"}``; schema
    validation errors (422) carry a list of per-field objects. Anything
    else (e.g. an HTML page from a proxy in front of the app) is
    returned as-is so nothing is swallowed.
    """
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            parts: list[str] = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                # Drop the leading "body" locator: the model thinks in
                # field names, not in request envelope structure.
                loc = ".".join(str(part) for part in item.get("loc", ())[1:])
                msg = str(item.get("msg", "invalid value"))
                parts.append(f"{loc}: {msg}" if loc else msg)
            if parts:
                return "; ".join(parts)
    # Unexpected shape: dump it, truncated — a proxy's HTML error page
    # must not blow up the model's context window.
    text = str(payload)
    if len(text) > 500:
        text = text[:500] + "…(truncated)"
    return text


class AurumClient:
    """Async client for one Aurum instance, built from ``AgentConfig``."""

    def __init__(
        self,
        config: AgentConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        auth = None
        if config.api_user is not None:
            # The pair is validated by load_config, but AgentConfig is a
            # plain dataclass — a half-filled pair constructed directly
            # fails fast here instead of silently sending a blank password.
            if config.api_password is None:
                raise ValueError("api_user is set but api_password is None")
            auth = (config.api_user, config.api_password)
        self._client = httpx.AsyncClient(
            base_url=config.api_url,
            auth=auth,
            timeout=REQUEST_TIMEOUT,
            transport=transport,
        )
        self._config = config

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Perform one HTTP call and return the parsed JSON body.

        ``AurumApiError`` is raised for transport failures and any 4xx/5xx
        response; ``204`` answers return ``None``. Retries are GET-only —
        see the module docstring for why writes never repeat themselves.
        """
        method = method.upper()
        # GET/HEAD are safe to repeat (reads); every Aurum endpoint is a
        # GET for reading, HEAD is kept only for the idempotency rule's
        # symmetry. Writes land here with retries=0 and never repeat.
        retries = GET_RETRIES if method in ("GET", "HEAD") else 0

        response: httpx.Response | None = None
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, params=params, json=json)
            except httpx.HTTPError as error:
                if attempt >= retries:
                    # Model-facing text: English matches the tool layer
                    # and the backend's own messages.
                    raise AurumApiError(
                        0,
                        f"Connection to {self._config.api_url} failed: {error!r}",
                    ) from error
                attempt += 1
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
            else:
                break

        # Runtime-checked invariant instead of an assert: asserts vanish
        # under `python -O`, and a refactor breaking the loop should fail
        # with a clear message, not an AttributeError downstream.
        if response is None:  # pragma: no cover - the loop always sets it
            raise AurumApiError(0, "internal error: no response")
        if response.is_error:
            try:
                payload: Any = response.json()
            except ValueError:
                # Not JSON at all — an HTML error page from nginx or a
                # proxy in front of the app. Surfaced raw, not swallowed.
                payload = response.text
            raise AurumApiError(response.status_code, format_error_detail(payload))
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as error:
            # Same "nothing is swallowed" rule on the success path: a
            # 2xx with a non-JSON body (a misrouted proxy) reaches the
            # model as an error it can report, not as a JSONDecodeError.
            raise AurumApiError(
                response.status_code,
                f"Non-JSON response from {self._config.api_url}: {error!r}",
            ) from error

    async def health(self) -> bool:
        """Pre-flight check: ``GET /health`` answers ``{"status": "ok"}``."""
        try:
            payload = await self.request("GET", HEALTH_PATH)
        except AurumApiError:
            return False
        return isinstance(payload, dict) and payload.get("status") == "ok"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AurumClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
