"""Transactions: creation rules, filtering, pagination, sorting, and the
/transactions/years picker endpoint.

These assert the actual contract the frontend relies on — e.g. the year/month
filter test below is the backend half of the "Recent Transactions showed last
month's data too" regression from Aug 2026 (see UPDATES.md): the bug was in
the frontend not passing year/month at all, but if the backend ever stopped
honoring those filters correctly, the frontend fix would silently stop
working and nothing would catch it except this test.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload as _txn


async def test_bulk_create_transactions(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                _txn(account_id, category_id=groceries, description="csv row 1", date="2026-01-01"),
                _txn(account_id, category_id=groceries, description="csv row 2", date="2026-01-02"),
            ]
        },
    )
    assert resp.status_code == 201
    assert resp.json()["created"] == 2

    listed = await client.get("/transactions", params={"year": 2026, "month": 1})
    assert listed.json()["total"] == 2


async def test_bulk_create_is_all_or_nothing(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    salary = categories["Salary"]["id"]
    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                _txn(account_id, category_id=groceries, description="good row"),
                # An expense using an income category — rejected, and it
                # should take the whole batch down with it.
                _txn(account_id, category_id=salary, description="bad row"),
            ]
        },
    )
    assert resp.status_code == 400

    listed = await client.get("/transactions")
    assert listed.json()["total"] == 0


async def test_create_expense_rejects_income_category(client: AsyncClient, account_id, categories):
    income_category = categories["Salary"]
    resp = await client.post(
        "/transactions", json=_txn(account_id, type="expense", category_id=income_category["id"])
    )
    assert resp.status_code == 400


async def test_create_capitalizes_description_first_letter(client: AsyncClient, account_id, categories):
    category = categories["Groceries"]
    resp = await client.post(
        "/transactions",
        json=_txn(account_id, category_id=category["id"], description="траты на продукты"),
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Траты на продукты"


async def test_update_capitalizes_description_first_letter(client: AsyncClient, account_id, categories):
    category = categories["Groceries"]
    created = await client.post("/transactions", json=_txn(account_id, category_id=category["id"]))
    txn_id = created.json()["id"]

    resp = await client.patch(f"/transactions/{txn_id}", json={"description": "new coffee shop"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "New coffee shop"


async def test_create_income_rejects_expense_category(client: AsyncClient, account_id, categories):
    expense_category = categories["Groceries"]
    resp = await client.post(
        "/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=expense_category["id"])
    )
    assert resp.status_code == 400


async def test_create_expense_with_matching_category_succeeds(client: AsyncClient, account_id, categories):
    category = categories["Groceries"]
    resp = await client.post("/transactions", json=_txn(account_id, category_id=category["id"]))
    assert resp.status_code == 201
    body = resp.json()
    assert body["category"]["id"] == category["id"]
    assert money(body["amount"]) == Decimal("10.00")


async def test_transfer_requires_destination_account(client: AsyncClient, account_id):
    resp = await client.post("/transactions", json=_txn(account_id, type="transfer", amount="50.00"))
    assert resp.status_code == 422


async def test_transfer_rejects_same_source_and_destination(client: AsyncClient, account_id):
    resp = await client.post(
        "/transactions",
        json=_txn(account_id, type="transfer", amount="50.00", transfer_account_id=account_id),
    )
    assert resp.status_code == 422


async def test_transfer_rejects_a_category(client: AsyncClient, account_id, categories):
    other = await client.post("/accounts", json={"name": "Savings", "type": "savings", "currency": "USD"})
    other_id = other.json()["id"]
    resp = await client.post(
        "/transactions",
        json=_txn(
            account_id,
            type="transfer",
            amount="50.00",
            transfer_account_id=other_id,
            category_id=categories["Groceries"]["id"],
        ),
    )
    assert resp.status_code == 422


async def test_valid_transfer_between_two_accounts_succeeds(client: AsyncClient, account_id):
    other = await client.post("/accounts", json={"name": "Savings", "type": "savings", "currency": "USD"})
    other_id = other.json()["id"]
    resp = await client.post(
        "/transactions", json=_txn(account_id, type="transfer", amount="50.00", transfer_account_id=other_id)
    )
    assert resp.status_code == 201


async def test_list_filters_by_year_and_month_excludes_other_months(client: AsyncClient, account_id, categories):
    """The exact shape of the Aug 2026 Dashboard bug: three transactions in
    three different months must never leak into a query scoped to just one
    of them."""
    category_id = categories["Groceries"]["id"]
    for txn_date, description in [
        ("2021-07-26", "july transaction"),
        ("2021-08-08", "august transaction"),
        ("2026-08-16", "current year august"),
    ]:
        resp = await client.post(
            "/transactions", json=_txn(account_id, category_id=category_id, date=txn_date, description=description)
        )
        assert resp.status_code == 201

    resp = await client.get("/transactions", params={"year": 2021, "month": 8})
    body = resp.json()
    assert body["total"] == 1
    assert [item["description"] for item in body["items"]] == ["August transaction"]


async def test_list_filters_by_explicit_date_range(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    for txn_date in ["2024-01-01", "2024-06-15", "2024-12-31"]:
        await client.post("/transactions", json=_txn(account_id, category_id=category_id, date=txn_date))

    resp = await client.get("/transactions", params={"start_date": "2024-02-01", "end_date": "2024-11-01"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["date"] == "2024-06-15"


async def test_search_matches_description_across_any_period_ignoring_month_filter(
    client: AsyncClient, account_id, categories
):
    """The point of search is finding a purchase from an unknown month without
    already knowing which month to filter by, so it must not be scoped by the
    year/month params even when the caller happens to also pass them."""
    category_id = categories["Groceries"]["id"]
    for txn_date, description in [
        ("2021-03-12", "PlayStation 5 console"),
        ("2024-11-02", "grocery run"),
        ("2026-08-16", "current month coffee"),
    ]:
        resp = await client.post(
            "/transactions", json=_txn(account_id, category_id=category_id, date=txn_date, description=description)
        )
        assert resp.status_code == 201

    resp = await client.get("/transactions", params={"search": "playstation"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["description"] == "PlayStation 5 console"


async def test_search_matches_merchant_and_notes(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post(
        "/transactions",
        json=_txn(account_id, category_id=category_id, description="misc", merchant="Best Buy"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, category_id=category_id, description="misc", notes="bought for a birthday gift"),
    )

    merchant_resp = await client.get("/transactions", params={"search": "best buy"})
    assert merchant_resp.json()["total"] == 1

    notes_resp = await client.get("/transactions", params={"search": "birthday"})
    assert notes_resp.json()["total"] == 1


async def test_search_with_no_matches_returns_empty(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, category_id=category_id, description="groceries"))

    resp = await client.get("/transactions", params={"search": "nonexistent item xyz"})
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_pagination_covers_every_item_with_no_overlap(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    for day in range(1, 26):
        await client.post(
            "/transactions",
            json=_txn(account_id, category_id=category_id, date=f"2025-03-{day:02d}", description=f"txn-{day}"),
        )

    seen_ids: set[int] = set()
    page = 1
    total = None
    while True:
        resp = await client.get("/transactions", params={"page": page, "page_size": 10, "sort": "date_desc"})
        body = resp.json()
        total = body["total"]
        if not body["items"]:
            break
        for item in body["items"]:
            assert item["id"] not in seen_ids, "pagination must not repeat an item across pages"
            seen_ids.add(item["id"])
        page += 1

    assert total == 25
    assert len(seen_ids) == 25


async def test_sort_amount_desc_and_asc_are_opposite_orders(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    for amount in ["5.00", "50.00", "20.00"]:
        await client.post("/transactions", json=_txn(account_id, category_id=category_id, amount=amount))

    desc = await client.get("/transactions", params={"sort": "amount_desc"})
    asc = await client.get("/transactions", params={"sort": "amount_asc"})
    desc_amounts = [money(item["amount"]) for item in desc.json()["items"]]
    asc_amounts = [money(item["amount"]) for item in asc.json()["items"]]
    assert desc_amounts == [Decimal("50.00"), Decimal("20.00"), Decimal("5.00")]
    assert asc_amounts == list(reversed(desc_amounts))


async def test_update_transaction_persists_changes(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    created = await client.post("/transactions", json=_txn(account_id, category_id=category_id))
    txn_id = created.json()["id"]

    resp = await client.patch(f"/transactions/{txn_id}", json={"amount": "99.99", "description": "updated"})
    assert resp.status_code == 200
    assert money(resp.json()["amount"]) == Decimal("99.99")
    assert resp.json()["description"] == "Updated"

    refetched = await client.get("/transactions", params={"page_size": 1})
    assert money(refetched.json()["items"][0]["amount"]) == Decimal("99.99")


async def test_update_transaction_rejects_category_kind_mismatch(client: AsyncClient, account_id, categories):
    created = await client.post(
        "/transactions", json=_txn(account_id, type="expense", category_id=categories["Groceries"]["id"])
    )
    txn_id = created.json()["id"]

    resp = await client.patch(f"/transactions/{txn_id}", json={"category_id": categories["Salary"]["id"]})
    assert resp.status_code == 400


async def test_delete_transaction_removes_it_from_listing(client: AsyncClient, account_id, categories):
    created = await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"])
    )
    txn_id = created.json()["id"]

    delete_resp = await client.delete(f"/transactions/{txn_id}")
    assert delete_resp.status_code == 204

    listing = await client.get("/transactions")
    assert txn_id not in [item["id"] for item in listing.json()["items"]]


async def test_years_endpoint_spans_earliest_transaction_through_current_year(
    client: AsyncClient, account_id, categories
):
    category_id = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, category_id=category_id, date="2021-03-01"))
    await client.post("/transactions", json=_txn(account_id, category_id=category_id, date="2023-11-20"))

    resp = await client.get("/transactions/years")
    current_year = date.today().year
    assert resp.json() == list(range(2021, current_year + 1))


async def test_years_endpoint_with_no_transactions_returns_only_current_year(client: AsyncClient):
    resp = await client.get("/transactions/years")
    assert resp.json() == [date.today().year]


async def test_update_cannot_turn_a_transaction_into_a_transfer_without_a_destination(
    client: AsyncClient, account_id, categories
):
    """The create path rejects a transfer with no transfer_account_id; the
    update path has to reject it too, or the row ends up moving money out of
    an account and into nowhere — account_service subtracts the amount from
    account_id but only credits transfer_account_id when it isn't NULL, so
    the balance (and Net Worth's cash line, which walks the same rows) just
    loses it."""
    created = await client.post(
        "/transactions", json=_txn(account_id, amount="40.00", category_id=categories["Groceries"]["id"])
    )
    txn_id = created.json()["id"]
    balance_before = money((await client.get("/accounts")).json()[0]["balance"])

    resp = await client.patch(f"/transactions/{txn_id}", json={"type": "transfer", "category_id": None})

    assert resp.status_code == 400
    assert money((await client.get("/accounts")).json()[0]["balance"]) == balance_before


async def test_update_rejects_a_transfer_pointing_at_its_own_account(client: AsyncClient, account_id):
    """Same rule as on create: a transfer to itself is a no-op row that still
    shows up in the ledger as a transfer."""
    other = (await client.post("/accounts", json={"name": "Savings", "type": "savings"})).json()
    created = await client.post(
        "/transactions", json=_txn(account_id, type="transfer", transfer_account_id=other["id"], category_id=None)
    )
    txn_id = created.json()["id"]

    resp = await client.patch(f"/transactions/{txn_id}", json={"transfer_account_id": account_id})

    assert resp.status_code == 400


async def test_update_rejects_a_transfer_destination_on_a_non_transfer(
    client: AsyncClient, account_id, categories
):
    """transfer_account_id on an expense is meaningless — balances only read
    it for TRANSFER rows — and create already refuses it."""
    other = (await client.post("/accounts", json={"name": "Savings", "type": "savings"})).json()
    created = await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"])
    )

    resp = await client.patch(
        f"/transactions/{created.json()['id']}", json={"transfer_account_id": other["id"]}
    )

    assert resp.status_code == 400


async def test_update_rejects_a_category_on_a_transfer(client: AsyncClient, account_id, categories):
    """A categorized transfer would be counted as spending by the reports that
    join on category — create rejects it, update must as well."""
    other = (await client.post("/accounts", json={"name": "Savings", "type": "savings"})).json()
    created = await client.post(
        "/transactions", json=_txn(account_id, type="transfer", transfer_account_id=other["id"], category_id=None)
    )

    resp = await client.patch(
        f"/transactions/{created.json()['id']}", json={"category_id": categories["Groceries"]["id"]}
    )

    assert resp.status_code == 400
