"""FX rules that do not need the integration test database."""
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services import fx_service


@pytest.mark.asyncio
async def test_historical_weekend_uses_rates_endpoint(monkeypatch):
    fx_service._cache.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/rates"
        assert request.url.params["date"] == "2026-10-25"
        return httpx.Response(200, json=[{
            "date": "2026-10-25", "base": "RUB", "quote": "USD", "rate": 0.0123,
        }])

    original_client = httpx.AsyncClient
    monkeypatch.setattr(fx_service.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    quote = await fx_service.rate_to_usd("RUB", date(2026, 10, 25))
    assert quote.rate == Decimal("0.0123")
    assert quote.date == date(2026, 10, 25)


@pytest.mark.asyncio
async def test_booked_amounts_keep_original_and_account_units(monkeypatch):
    async def fake_rate(currency: str, on_date: date) -> fx_service.FxQuote:
        return fx_service.FxQuote({"USD": Decimal("1"), "EUR": Decimal("1.2"), "RUB": Decimal("0.012")}[currency], on_date)

    monkeypatch.setattr(fx_service, "rate_to_usd", fake_rate)
    result = await fx_service.booked_amounts(Decimal("10"), "EUR", "RUB", "USD", date(2026, 1, 15))
    assert result["amount_usd"] == Decimal("12.00")
    assert result["account_amount"] == Decimal("1000.00")
    assert result["transfer_amount"] == Decimal("12.00")
