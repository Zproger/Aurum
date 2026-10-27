"""Account-type behavior shared by the accounts API and financial summaries."""
from datetime import date

from httpx import AsyncClient
from decimal import Decimal

from app.services import account_service, fx_service, net_worth_service

from tests.helpers import money, txn_payload


async def test_debit_card_is_a_liquid_account_type(client: AsyncClient, categories, monkeypatch):
    async def fixed_rate(currency: str, on_date: date) -> fx_service.FxQuote:
        return fx_service.FxQuote(Decimal("0.012") if currency == "RUB" else Decimal("1"), on_date)

    monkeypatch.setattr(fx_service, "rate_to_usd", fixed_rate)
    monkeypatch.setattr(account_service, "rate_to_usd", fixed_rate)
    monkeypatch.setattr(net_worth_service, "rate_to_usd", fixed_rate)
    response = await client.post(
        "/accounts",
        json={"name": "Debit card", "type": "debit_card", "currency": "RUB"},
    )

    assert response.status_code == 201
    debit_card = response.json()
    assert debit_card["type"] == "debit_card"

    transaction = await client.post(
        "/transactions",
        json=txn_payload(
            debit_card["id"],
            type="income",
            amount="1000.00",
            category_id=categories["Salary"]["id"],
            date=date.today().isoformat(),
        ),
    )
    assert transaction.status_code == 201

    summary = await client.get("/net-worth/summary", params={"range": "all"})

    assert summary.status_code == 200
    assert money(summary.json()["current"]) == money("12.00")
