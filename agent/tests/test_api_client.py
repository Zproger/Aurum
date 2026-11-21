"""API client tests over a mock transport: auth, idempotent retries, errors."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from aurum_agent.api_client import AurumApiError, AurumClient
from aurum_agent.config import AgentConfig


def make_config(**overrides: Any) -> AgentConfig:
    values: dict[str, Any] = dict(
        api_url="http://test.local/api",
        api_user=None,
        api_password=None,
        llm_base_url="https://llm.local/v1",
        llm_model="test-model",
        llm_api_key="k",
    )
    values.update(overrides)
    return AgentConfig(**values)


def make_client(
    handler: httpx.MockTransport.handler_type,
    monkeypatch: pytest.MonkeyPatch | None = None,
    **config_overrides: Any,
) -> AurumClient:
    if monkeypatch is not None:
        # Real backoff would only slow the retry tests down.
        monkeypatch.setattr("aurum_agent.api_client.RETRY_BACKOFF_SECONDS", 0)
    return AurumClient(make_config(**config_overrides), transport=httpx.MockTransport(handler))


def json_handler(payload: Any, status: int = 200) -> httpx.MockTransport.handler_type:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


async def test_request_joins_base_url_and_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async with make_client(handler) as client:
        await client.request("GET", "/accounts")

    assert str(seen[0].url) == "http://test.local/api/accounts"


async def test_basic_auth_header_is_sent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    async with make_client(handler, api_user="misha", api_password="secret") as client:
        await client.request("GET", "/accounts")

    assert seen[0].headers["Authorization"] == "Basic bWlzaGE6c2VjcmV0"


async def test_no_auth_header_by_default() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    async with make_client(handler) as client:
        await client.request("GET", "/accounts")

    assert "Authorization" not in seen[0].headers


async def test_get_is_retried_on_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            # Simulate a flaky network: the first two attempts never land.
            raise httpx.ConnectError("flaky", request=request)
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, monkeypatch)
    payload = await client.request("GET", "/accounts")

    assert payload == {"ok": True}
    assert len(calls) == 3


async def test_post_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler, monkeypatch)
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("POST", "/transactions", json={"x": 1})

    # One attempt only: a retried write could have already been applied.
    assert len(calls) == 1
    assert exc_info.value.status == 0


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
async def test_writes_are_never_retried(method: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler, monkeypatch)
    with pytest.raises(AurumApiError):
        await client.request(method, "/categories/1", json={"name": "x"})

    assert len(calls) == 1


async def test_business_error_message_passes_through() -> None:
    client = make_client(
        json_handler({"detail": "Category 'Salary' is a income category"}, status=400)
    )
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("POST", "/transactions", json={})

    assert exc_info.value.status == 400
    assert "income category" in exc_info.value.detail


async def test_validation_error_fields_are_formatted() -> None:
    payload = {
        "detail": [
            {"loc": ["body", "amount"], "msg": "Field required", "type": "missing"},
            {"loc": ["body", "date"], "msg": "Input should be a valid date", "type": "date_from_date_parsing"},
        ]
    }
    client = make_client(json_handler(payload, status=422))
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("POST", "/transactions", json={})

    assert exc_info.value.status == 422
    assert "amount: Field required" in exc_info.value.detail
    assert "date: Input should be a valid date" in exc_info.value.detail


async def test_non_json_error_body_is_not_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    client = make_client(handler)
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("GET", "/accounts")

    assert exc_info.value.status == 502
    # No FastAPI "detail" here — the raw body is surfaced instead.
    assert "Bad Gateway" in exc_info.value.detail


async def test_huge_error_body_is_truncated_for_the_model() -> None:
    # A proxy's HTML error page must not blow up the model's context.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>" + "x" * 2000 + "</html>")

    client = make_client(handler)
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("GET", "/accounts")

    assert "(truncated)" in exc_info.value.detail
    assert len(exc_info.value.detail) < 600


async def test_delete_returns_none_on_204() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = make_client(handler)
    assert await client.request("DELETE", "/transactions/1") is None


async def test_transport_error_message_names_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client = make_client(handler, monkeypatch)
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("GET", "/accounts")

    assert exc_info.value.status == 0
    assert "http://test.local/api" in exc_info.value.detail


async def test_health_true_on_ok() -> None:
    client = make_client(json_handler({"status": "ok"}))
    assert await client.health() is True


async def test_health_false_on_error() -> None:
    client = make_client(json_handler({"detail": "boom"}, status=500))
    assert await client.health() is False


async def test_health_false_on_unexpected_body() -> None:
    # Anything that is not {"status": "ok"} means "cannot rely on the
    # instance" — same answer as a hard error.
    client = make_client(json_handler({"status": "unexpected"}))
    assert await client.health() is False


async def test_half_filled_auth_pair_is_rejected() -> None:
    # Direct AgentConfig construction with a missing password must fail
    # here rather than silently send a blank one.
    with pytest.raises(ValueError, match="api_password"):
        AurumClient(make_config(api_user="misha", api_password=None))


async def test_success_body_with_garbage_json_is_an_api_error() -> None:
    # A 2xx with a non-JSON body (a misrouted proxy) surfaces as an
    # AurumApiError instead of a raw JSONDecodeError crashing the graph.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not aurum</html>")

    client = make_client(handler)
    with pytest.raises(AurumApiError) as exc_info:
        await client.request("GET", "/accounts")

    assert exc_info.value.status == 200
    assert "Non-JSON response" in exc_info.value.detail
