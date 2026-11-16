"""Tag reports: the ranking (which tag cost the most over a period, and on
what) and the single-tag spending detail.

What separates these from the category reports in test_reports.py is that a
tag lives on the transaction, not on a category or a split line
(models/tag.py) — so a tagged transaction counts in full toward its tag
however its categories are split, and two tags on one transaction each
count it whole.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload as _txn


async def _tag(client: AsyncClient, name: str) -> int:
    return (await client.post("/tags", json={"name": name})).json()["id"]


async def test_ranking_sums_a_tag_across_categories(client: AsyncClient, account_id, categories):
    """The point of the report: one tag's total cutting across the
    categories the category ranking would have scattered it over."""
    together = await _tag(client, "together")
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="60.00", category_id=categories["Dining Out"]["id"], tag_ids=[together]),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="40.00", category_id=categories["Shopping"]["id"], tag_ids=[together]),
    )

    resp = await client.get("/reports/tag-ranking", params={"kind": "expense"})
    assert resp.status_code == 200
    item = resp.json()["items"][0]

    assert item["name"] == "together"
    assert money(item["amount"]) == Decimal("100.00")
    assert item["transaction_count"] == 2
    breakdown = {c["name"]: money(c["amount"]) for c in item["categories"]}
    assert breakdown == {"Dining Out": Decimal("60.00"), "Shopping": Decimal("40.00")}


async def test_ranking_counts_a_split_transaction_whole_but_breaks_it_down(client: AsyncClient, account_id, categories):
    """A split decides how the tag's total is attributed inside the
    breakdown, never how much the tag itself is worth."""
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post(
            "/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries}
        )
    ).json()["id"]
    gifts = await _tag(client, "gifts")
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            tag_ids=[gifts],
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )

    item = (await client.get("/reports/tag-ranking", params={"kind": "expense"})).json()["items"][0]

    assert money(item["amount"]) == Decimal("100.00")
    assert item["transaction_count"] == 1
    # Rolled up to the top-level category, same as everywhere else in the app.
    assert [(c["name"], money(c["amount"])) for c in item["categories"]] == [("Groceries", Decimal("100.00"))]


async def test_two_tags_on_one_transaction_each_count_it_whole(client: AsyncClient, account_id, categories):
    date_night = await _tag(client, "date-night")
    anniversary = await _tag(client, "anniversary")
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="80.00",
            category_id=categories["Dining Out"]["id"],
            tag_ids=[date_night, anniversary],
        ),
    )

    body = (await client.get("/reports/tag-ranking", params={"kind": "expense"})).json()
    amounts = {item["name"]: money(item["amount"]) for item in body["items"]}

    assert amounts == {"date-night": Decimal("80.00"), "anniversary": Decimal("80.00")}
    # Overlapping tags must not inflate the period's own totals: the
    # transaction is one 80.00 expense, counted once on both lines.
    assert money(body["total_amount"]) == Decimal("80.00")
    assert money(body["tagged_amount"]) == Decimal("80.00")


async def test_percent_is_measured_against_all_spending_not_just_tagged(client: AsyncClient, account_id, categories):
    gifts = await _tag(client, "gifts")
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Shopping"]["id"], tag_ids=[gifts]),
    )
    await client.post("/transactions", json=_txn(account_id, amount="75.00", category_id=categories["Groceries"]["id"]))

    body = (await client.get("/reports/tag-ranking", params={"kind": "expense"})).json()

    assert money(body["total_amount"]) == Decimal("100.00")
    assert money(body["tagged_amount"]) == Decimal("25.00")
    assert body["items"][0]["percent"] == 25.0


async def test_ranking_keeps_an_uncategorized_amount_in_its_own_bucket(client: AsyncClient, account_id):
    """A transaction saved without a category is still real money the tag
    owns — it gets a null-category bucket rather than dropping out of the
    breakdown and leaving it short of the tag's total."""
    misc = await _tag(client, "misc")
    await client.post("/transactions", json=_txn(account_id, amount="15.00", category_id=None, tag_ids=[misc]))

    item = (await client.get("/reports/tag-ranking", params={"kind": "expense"})).json()["items"][0]

    assert money(item["amount"]) == Decimal("15.00")
    assert [(c["category_id"], money(c["amount"])) for c in item["categories"]] == [(None, Decimal("15.00"))]


async def test_ranking_respects_kind_and_date_range(client: AsyncClient, account_id, categories):
    shared = await _tag(client, "shared")
    dining = categories["Dining Out"]["id"]
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="30.00", category_id=dining, tag_ids=[shared], date="2026-03-10"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="50.00", category_id=dining, tag_ids=[shared], date="2026-07-10"),
    )
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            type="income",
            amount="900.00",
            category_id=categories["Salary"]["id"],
            tag_ids=[shared],
            date="2026-03-05",
        ),
    )

    ranged = await client.get(
        "/reports/tag-ranking",
        params={"kind": "expense", "start_date": "2026-01-01", "end_date": "2026-06-30"},
    )
    assert money(ranged.json()["items"][0]["amount"]) == Decimal("30.00")

    income = await client.get("/reports/tag-ranking", params={"kind": "income"})
    assert money(income.json()["items"][0]["amount"]) == Decimal("900.00")


async def test_tag_spending_report_series_fills_gap_months(client: AsyncClient, account_id, categories):
    trip = await _tag(client, "trip")
    dining = categories["Dining Out"]["id"]
    await client.post(
        "/transactions", json=_txn(account_id, amount="10.00", category_id=dining, tag_ids=[trip], date="2026-01-15")
    )
    await client.post(
        "/transactions", json=_txn(account_id, amount="20.00", category_id=dining, tag_ids=[trip], date="2026-03-15")
    )

    body = (await client.get("/reports/tag-spending", params={"tag_id": trip})).json()

    assert body["tag_name"] == "trip"
    assert money(body["total_amount"]) == Decimal("30.00")
    assert body["transaction_count"] == 2
    assert [(p["month"], money(p["amount"])) for p in body["series"]] == [
        (1, Decimal("10.00")),
        (2, Decimal("0")),
        (3, Decimal("20.00")),
    ]
    assert money(body["average_per_month"]) == Decimal("10.00")


async def test_tag_spending_report_counts_a_split_transaction_once(client: AsyncClient, account_id, categories):
    """The category detail report has to de-duplicate split lines; the tag
    one never sees them, so a split transaction is one row worth its full
    amount."""
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post(
            "/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries}
        )
    ).json()["id"]
    trip = await _tag(client, "trip")
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            tag_ids=[trip],
            splits=[
                {"category_id": groceries, "amount": "60.00"},
                {"category_id": sweets, "amount": "40.00"},
            ],
        ),
    )

    body = (await client.get("/reports/tag-spending", params={"tag_id": trip})).json()

    assert money(body["total_amount"]) == Decimal("100.00")
    assert body["transaction_count"] == 1


async def test_tag_spending_report_is_empty_for_an_unused_tag(client: AsyncClient):
    unused = await _tag(client, "unused")

    body = (await client.get("/reports/tag-spending", params={"tag_id": unused})).json()

    assert money(body["total_amount"]) == Decimal("0")
    assert body["series"] == []


async def test_tag_spending_report_404s_for_a_missing_tag(client: AsyncClient):
    assert (await client.get("/reports/tag-spending", params={"tag_id": 9999})).status_code == 404


async def test_ranking_is_empty_when_nothing_is_tagged(client: AsyncClient, account_id, categories):
    await client.post("/transactions", json=_txn(account_id, amount="10.00", category_id=categories["Groceries"]["id"]))

    body = (await client.get("/reports/tag-ranking", params={"kind": "expense"})).json()

    assert body["items"] == []
    assert money(body["tagged_amount"]) == Decimal("0")
    assert money(body["total_amount"]) == Decimal("10.00")
