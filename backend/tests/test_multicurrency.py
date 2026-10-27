"""Money is booked in account units and reported in USD."""
from datetime import date
from decimal import Decimal

import pytest

from app.services import account_service, crypto_service, fx_service, insights_service, net_worth_service
from tests.helpers import money


@pytest.fixture(autouse=True)
def deterministic_rates(monkeypatch):
    async def rate(currency: str, on_date: date) -> fx_service.FxQuote:
        rates = {"USD": Decimal("1"), "EUR": Decimal("1.2"), "RUB": Decimal("0.012")}
        return fx_service.FxQuote(rates[currency], on_date)

    for module in (fx_service, account_service, crypto_service, insights_service, net_worth_service):
        monkeypatch.setattr(module, "rate_to_usd", rate)


async def test_foreign_expense_updates_account_and_usd_reports(client, categories):
    account = (await client.post("/accounts", json={"name": "Ruble card", "currency": "RUB"})).json()
    created = await client.post("/transactions", json={
        "account_id": account["id"], "category_id": categories["Groceries"]["id"],
        "type": "expense", "amount": "10.00", "currency": "EUR",
        "description": "Groceries", "date": date.today().isoformat(),
    })
    assert created.status_code == 201
    transaction = created.json()
    assert transaction["currency"] == "EUR"
    assert money(transaction["amount_usd"]) == money("12")
    assert money(transaction["account_amount"]) == money("1000")

    balances = (await client.get("/accounts")).json()
    ruble = next(row for row in balances if row["id"] == account["id"])
    assert money(ruble["balance"]) == money("-1000")
    assert money(ruble["balance_usd"]) == money("-12")

    today = date.today()
    summary = (await client.get("/dashboard/summary", params={"year": today.year, "month": today.month})).json()
    assert money(summary["spent"]) == money("12")


async def test_transfer_books_two_account_currencies_and_actual_received_amount(client):
    source = (await client.post("/accounts", json={"name": "RUB", "currency": "RUB"})).json()
    destination = (await client.post("/accounts", json={"name": "EUR", "currency": "EUR"})).json()
    created = await client.post("/transactions", json={
        "account_id": source["id"], "transfer_account_id": destination["id"],
        "type": "transfer", "amount": "12.00", "currency": "USD",
        "transfer_amount": "9.50", "description": "Exchange", "date": date.today().isoformat(),
    })
    assert created.status_code == 201
    assert money(created.json()["account_amount"]) == money("1000")
    assert money(created.json()["transfer_amount"]) == money("9.50")
    balances = {row["id"]: row for row in (await client.get("/accounts")).json()}
    assert money(balances[source["id"]]["balance"]) == money("-1000")
    assert money(balances[destination["id"]]["balance"]) == money("9.50")


async def test_bank_statement_amount_can_override_reference_conversion(client):
    account = (await client.post("/accounts", json={"name": "Ruble card", "currency": "RUB"})).json()
    created = await client.post("/transactions", json={
        "account_id": account["id"], "type": "expense", "amount": "10.00", "currency": "EUR",
        "account_amount": "990.00", "description": "Purchase", "date": date.today().isoformat(),
    })
    assert created.status_code == 201
    assert money(created.json()["amount_usd"]) == money("12")
    assert money(created.json()["account_amount"]) == money("990")
    balance = next(row for row in (await client.get("/accounts")).json() if row["id"] == account["id"])
    assert money(balance["balance"]) == money("-990")


async def test_quote_and_account_currency_guard(client):
    account = (await client.post("/accounts", json={"name": "Ruble card", "currency": "RUB"})).json()
    quoted = await client.get("/transactions/quote", params={
        "amount": "10", "currency": "EUR", "date": date.today().isoformat(), "account_id": account["id"],
    })
    assert quoted.status_code == 200
    assert money(quoted.json()["amount_usd"]) == money("12")
    assert money(quoted.json()["account_amount"]) == money("1000")
    created = await client.post("/transactions", json={
        "account_id": account["id"], "type": "income", "amount": "1", "currency": "RUB",
        "description": "Opening", "date": date.today().isoformat(),
    })
    assert created.status_code == 201
    changed = await client.patch(f"/accounts/{account['id']}", json={"currency": "EUR"})
    assert changed.status_code == 400


async def test_recurring_uses_rate_when_posted(client, categories):
    account = (await client.post("/accounts", json={"name": "Ruble card", "currency": "RUB"})).json()
    template = await client.post("/recurring", json={
        "account_id": account["id"], "type": "expense", "amount": "10.00", "currency": "EUR",
        "description": "Subscription", "frequency": "monthly", "anchor_date": date.today().isoformat(),
        "category_id": categories["Subscriptions"]["id"],
    })
    assert template.status_code == 201
    posted = await client.post(f"/recurring/{template.json()['id']}/post")
    assert posted.status_code == 201
    transaction = (await client.get("/transactions")).json()["items"][0]
    assert transaction["currency"] == "EUR"
    assert money(transaction["amount_usd"]) == money("12")


async def test_edit_reprices_transaction_and_split_usd_amounts(client, account_id, categories):
    parent = categories["Groceries"]["id"]
    child = (await client.post("/categories", json={
        "name": "Fruit", "kind": "expense", "parent_id": parent,
        "color": "#2a78d6", "sort_order": 50,
    })).json()["id"]
    created = await client.post("/transactions", json={
        "account_id": account_id, "type": "expense", "amount": "10.00",
        "description": "Market", "date": date.today().isoformat(),
        "splits": [{"category_id": parent, "amount": "3.00"}, {"category_id": child, "amount": "7.00"}],
    })
    assert created.status_code == 201
    changed = await client.patch(f"/transactions/{created.json()['id']}", json={"currency": "EUR"})
    assert changed.status_code == 200
    assert money(changed.json()["amount_usd"]) == money("12")
    assert sum((money(row["amount_usd"]) for row in changed.json()["splits"]), Decimal("0")) == Decimal("12")


async def test_backup_retains_fx_snapshot(client, account_id):
    created = await client.post("/transactions", json={
        "account_id": account_id, "type": "income", "amount": "10.00",
        "currency": "EUR", "description": "Gift", "date": date.today().isoformat(),
    })
    assert created.status_code == 201
    export = (await client.get("/backup/export")).json()
    assert export["transactions"][0]["currency"] == "EUR"
    restored = await client.post("/backup/import", json=export)
    assert restored.status_code == 200
    transaction = (await client.get("/transactions")).json()["items"][0]
    assert money(transaction["amount_usd"]) == money("12")


async def test_crypto_trade_retains_entered_currency_and_usd_cost_basis(client, monkeypatch):
    async def market_data(ids, vs_currency):
        return {"bitcoin": crypto_service._MarketPoint(Decimal("50000"), None, None, None)}

    monkeypatch.setattr(crypto_service, "_fetch_market_data", market_data)
    holding = await client.post("/crypto/holdings", json={
        "coingecko_id": "bitcoin", "symbol": "BTC", "name": "Bitcoin",
        "quantity": "1", "price_per_unit": "40000", "date": date.today().isoformat(),
    })
    assert holding.status_code == 201
    asset_id = holding.json()["asset_id"]
    added = await client.post(f"/crypto/holdings/{asset_id}/transactions", json={
        "type": "buy", "quantity": "1", "price_per_unit": "2500",
        "price_currency": "EUR", "date": date.today().isoformat(),
    })
    assert added.status_code == 201
    transactions = (await client.get(f"/crypto/holdings/{asset_id}/transactions")).json()
    eur_trade = next(row for row in transactions if row["price_currency"] == "EUR")
    assert money(eur_trade["price_per_unit_original"]) == money("2500")
    assert money(eur_trade["price_per_unit"]) == money("3000")
    assert money(added.json()["avg_buy_price"]) == money("21500")
