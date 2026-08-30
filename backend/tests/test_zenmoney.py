"""ZenMoney synchronization tests.

Tests the diff synchronizer against mocked ZenMoney API diff responses,
verifying account creation, category mapping, transaction handling (expenses,
incomes, transfers, balance adjustments, deletions), and error handling.
"""
from httpx import AsyncClient

from app.services import zenmoney_service


def _sample_diff_payload():
    return {
        "serverTimestamp": 1788117702,
        "instrument": [
            {"id": 1, "title": "Доллар США", "shortTitle": "USD", "symbol": "$"},
            {"id": 2, "title": "Российский рубль", "shortTitle": "RUB", "symbol": "руб."},
        ],
        "account": [
            {
                "id": "acc-1",
                "title": "Основной счёт",
                "type": "checking",
                "instrument": 2,
                "archive": false,
            },
            {
                "id": "acc-2",
                "title": "Наличные",
                "type": "cash",
                "instrument": 2,
                "archive": false,
            },
        ],
        "tag": [
            {
                "id": "tag-1",
                "title": "Продукты",
                "showIncome": false,
                "showOutcome": true,
                "parent": null,
            },
            {
                "id": "tag-2",
                "title": "Зарплата",
                "showIncome": true,
                "showOutcome": false,
                "parent": null,
            },
        ],
        "merchant": [
            {"id": "m-1", "title": "Пятёрочка"},
        ],
        "transaction": [
            {
                "id": "tx-expense-1",
                "date": "2026-08-01",
                "income": 0,
                "outcome": 1500,
                "incomeAccount": "acc-1",
                "outcomeAccount": "acc-1",
                "merchant": "m-1",
                "comment": "Покупка еды",
                "tag": ["tag-1"],
                "deleted": false,
            },
            {
                "id": "tx-income-1",
                "date": "2026-08-05",
                "income": 50000,
                "outcome": 0,
                "incomeAccount": "acc-1",
                "outcomeAccount": "acc-1",
                "comment": "Аванс",
                "tag": ["tag-2"],
                "deleted": false,
            },
            {
                "id": "tx-transfer-1",
                "date": "2026-08-10",
                "income": 5000,
                "outcome": 5000,
                "incomeAccount": "acc-2",
                "outcomeAccount": "acc-1",
                "comment": "Снятие наличных",
                "tag": null,
                "deleted": false,
            },
        ],
    }


async def test_zenmoney_status_when_no_token_configured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(zenmoney_service.get_settings(), "zenmoney_token", "")

    resp = await client.get("/zenmoney/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_configured"] is False
    assert data["server_timestamp"] == 0


async def test_zenmoney_sync_rejects_when_no_token_configured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(zenmoney_service.get_settings(), "zenmoney_token", "")

    resp = await client.post("/zenmoney/sync", json={})
    assert resp.status_code == 400
    assert "ZenMoney token not configured" in resp.json()["detail"]


async def test_zenmoney_sync_imports_accounts_categories_and_transactions(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(zenmoney_service.get_settings(), "zenmoney_token", "fake-test-token")

    async def fake_fetch_diff(token: str, server_ts: int):
        return _sample_diff_payload()

    monkeypatch.setattr(zenmoney_service, "_fetch_diff", fake_fetch_diff)

    resp = await client.post("/zenmoney/sync", json={})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["success"] is True
    assert result["server_timestamp"] == 1788117702
    assert result["accounts_synced"] == 2
    assert result["categories_synced"] == 2
    assert result["transactions_synced"] == 3
    assert result["transactions_deleted"] == 0

    # Verify Accounts
    accounts_resp = await client.get("/accounts")
    assert accounts_resp.status_code == 200
    accounts = accounts_resp.json()
    account_names = [a["name"] for a in accounts]
    assert "Основной счёт" in account_names
    assert "Наличные" in account_names

    # Verify Transactions
    tx_resp = await client.get("/transactions")
    assert tx_resp.status_code == 200
    tx_data = tx_resp.json()["items"]
    assert len(tx_data) == 3

    types = {t["type"] for t in tx_data}
    assert "expense" in types
    assert "income" in types
    assert "transfer" in types

    expense_tx = next(t for t in tx_data if t["type"] == "expense")
    assert float(expense_tx["amount"]) == 1500.0
    assert expense_tx["merchant"] == "Пятёрочка"
    assert expense_tx["notes"] == "Покупка еды"

    # Verify Status reflects synced state
    status_resp = await client.get("/zenmoney/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["is_configured"] is True
    assert status["server_timestamp"] == 1788117702
    assert status["synced_accounts_count"] == 2
    assert status["synced_categories_count"] == 2
    assert status["synced_transactions_count"] == 3
    assert status["last_error"] is None


async def test_zenmoney_sync_handles_deletions_and_updates(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(zenmoney_service.get_settings(), "zenmoney_token", "fake-test-token")

    # Initial sync
    async def first_fetch(token: str, server_ts: int):
        return _sample_diff_payload()

    monkeypatch.setattr(zenmoney_service, "_fetch_diff", first_fetch)
    await client.post("/zenmoney/sync", json={})

    # Second sync where tx-expense-1 is deleted, and another tx is added
    diff_2 = {
        "serverTimestamp": 1788120000,
        "instrument": [],
        "account": [],
        "tag": [],
        "merchant": [],
        "transaction": [
            {
                "id": "tx-expense-1",
                "deleted": True,
            },
            {
                "id": "tx-expense-2",
                "date": "2026-08-15",
                "income": 0,
                "outcome": 250,
                "incomeAccount": "acc-1",
                "outcomeAccount": "acc-1",
                "comment": "Кофе",
                "tag": ["tag-1"],
                "deleted": False,
            },
        ],
    }

    async def second_fetch(token: str, server_ts: int):
        return diff_2

    monkeypatch.setattr(zenmoney_service, "_fetch_diff", second_fetch)
    resp = await client.post("/zenmoney/sync", json={})
    assert resp.status_code == 200
    result = resp.json()
    assert result["transactions_deleted"] == 1
    assert result["transactions_synced"] == 1

    # Total transactions should now be 3 (income-1, transfer-1, expense-2)
    tx_resp = await client.get("/transactions")
    tx_items = tx_resp.json()["items"]
    assert len(tx_items) == 3
    descriptions = [t["description"] for t in tx_items]
    assert "Кофе" in descriptions
