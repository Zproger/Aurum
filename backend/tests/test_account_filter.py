"""The shared analytics account filter (?account_ids=…): Dashboard, Cash
Flow, both category reports and the transaction list must all narrow to the
selected accounts, and leave everything unchanged when no filter is sent."""
from httpx import AsyncClient

from tests.helpers import money, txn_payload as _txn


async def _second_account(client: AsyncClient) -> int:
    resp = await client.post("/accounts", json={"name": "Cash wallet", "type": "cash", "currency": "KZT"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed(client: AsyncClient, main: int, wallet: int, categories: dict) -> None:
    salary = categories["Salary"]["id"]
    groceries = categories["Groceries"]["id"]
    dining = categories["Dining Out"]["id"]
    for payload in (
        _txn(main, type="income", amount="1000.00", category_id=salary, date="2026-08-01"),
        _txn(main, type="expense", amount="300.00", category_id=groceries, date="2026-08-05"),
        _txn(wallet, type="expense", amount="50.00", category_id=dining, date="2026-08-06"),
        # A transfer is never income or spending, whichever accounts are selected.
        _txn(main, type="transfer", amount="200.00", transfer_account_id=wallet, transfer_amount="200.00",
             category_id=None, date="2026-08-07"),
    ):
        resp = await client.post("/transactions", json=payload)
        assert resp.status_code == 201, resp.text


async def test_dashboard_narrows_totals_categories_and_balance(client: AsyncClient, account_id, categories):
    wallet = await _second_account(client)
    await _seed(client, account_id, wallet, categories)
    month = {"year": 2026, "month": 8}

    everything = (await client.get("/dashboard/summary", params=month)).json()
    only_main = (await client.get("/dashboard/summary", params={**month, "account_ids": [account_id]})).json()
    only_wallet = (await client.get("/dashboard/summary", params={**month, "account_ids": [wallet]})).json()

    assert (money(everything["real_income"]), money(everything["spent"])) == (1000, 350)
    assert (money(only_main["real_income"]), money(only_main["spent"])) == (1000, 300)
    assert (money(only_wallet["real_income"]), money(only_wallet["spent"])) == (0, 50)
    assert [row["name"] for row in only_wallet["spending_by_category"]] == ["Dining Out"]
    # Balance: main 1000 - 300 - 200 = 500, wallet 200 - 50 = 150.
    assert money(everything["balance"]["total"]) == 650
    assert money(only_main["balance"]["total"]) == 500
    assert money(only_wallet["balance"]["total"]) == 150


async def test_cash_flow_and_reports_respect_the_same_filter(client: AsyncClient, account_id, categories):
    wallet = await _second_account(client)
    await _seed(client, account_id, wallet, categories)
    period = {"start_date": "2026-08-01", "end_date": "2026-08-31"}

    flow = (await client.get("/cash-flow", params={**period, "account_ids": [wallet]})).json()
    assert (money(flow["total_income"]), money(flow["total_expense"])) == (0, 50)

    ranking = (await client.get("/reports/category-ranking", params={**period, "account_ids": [account_id]})).json()
    assert [row["name"] for row in ranking["items"]] == ["Groceries"]
    assert money(ranking["total_amount"]) == 300

    groceries = categories["Groceries"]["id"]
    spending = (
        await client.get("/reports/category-spending", params={**period, "category_id": groceries, "account_ids": [wallet]})
    ).json()
    assert money(spending["total_amount"]) == 0


async def test_transaction_list_accepts_several_accounts(client: AsyncClient, account_id, categories):
    wallet = await _second_account(client)
    await _seed(client, account_id, wallet, categories)

    both = (await client.get("/transactions", params={"account_ids": [account_id, wallet]})).json()
    wallet_only = (await client.get("/transactions", params={"account_ids": [wallet]})).json()

    assert both["total"] == 4
    assert {item["account_id"] for item in wallet_only["items"]} == {wallet}


async def test_unknown_account_ids_cannot_widen_the_result(client: AsyncClient, account_id, categories):
    wallet = await _second_account(client)
    await _seed(client, account_id, wallet, categories)

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8, "account_ids": [999999]})).json()

    assert (money(body["real_income"]), money(body["spent"])) == (0, 0)
    assert money(body["balance"]["total"]) == 0
