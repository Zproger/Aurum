"""Crypto holdings: buy/sell transaction log, weighted-average cost basis,
and the lazy/forced price sync. CoinGecko itself is never called in tests —
services/crypto_service.py's _fetch_market_data is monkeypatched with a
canned market-data feed instead, same way any external dependency would be.
"""
from decimal import Decimal

import httpx
from httpx import AsyncClient

from app.services import crypto_service
from tests.helpers import money


def _point(price: str, change_1h: str | None = None, change_24h: str | None = None, change_7d: str | None = None):
    return crypto_service._MarketPoint(
        price=Decimal(price),
        change_1h=Decimal(change_1h) if change_1h else None,
        change_24h=Decimal(change_24h) if change_24h else None,
        change_7d=Decimal(change_7d) if change_7d else None,
    )


def _fake_fetch(prices: dict[str, "crypto_service._MarketPoint"]):
    async def fetch(coingecko_ids, vs_currency):
        return {cid: prices[cid] for cid in coingecko_ids if cid in prices}

    return fetch


async def _add_bitcoin(
    client: AsyncClient,
    quantity: str = "0.5",
    price_per_unit: str = "40000",
    risk_level: str | None = None,
    network: str | None = None,
) -> dict:
    payload = {
        "coingecko_id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "quantity": quantity,
        "price_per_unit": price_per_unit,
        "date": "2026-01-01",
    }
    if risk_level is not None:
        payload["risk_level"] = risk_level
    if network is not None:
        payload["network"] = network
    resp = await client.post("/crypto/holdings", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_holding_seeds_todays_value_and_position_immediately(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client, "0.5", "40000")

    assert holding["symbol"] == "BTC"  # normalized to uppercase
    assert money(holding["quantity"]) == money("0.5")
    assert money(holding["avg_buy_price"]) == money("40000")
    assert money(holding["current_price"]) == money("50000")
    assert money(holding["value"]) == money("25000")  # 0.5 * 50000
    assert money(holding["cost_basis"]) == money("20000")  # 0.5 * 40000
    assert money(holding["profit_loss"]) == money("5000")
    assert round(holding["profit_loss_percent"], 2) == 25.0


async def test_holding_shows_up_in_net_worth_breakdown(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "1", "40000")

    resp = await client.get("/net-worth/summary")

    breakdown = {item["key"]: item for item in resp.json()["breakdown"]}
    assert money(breakdown["crypto"]["amount"]) == money("50000")


async def test_second_buy_blends_into_weighted_average_cost(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")  # cost basis: 40000

    async def fail_if_called(coingecko_ids, vs_currency):
        raise AssertionError("adding a transaction must not call CoinGecko")

    monkeypatch.setattr(crypto_service, "_fetch_market_data", fail_if_called)

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert money(body["quantity"]) == money("2")
    # (1*40000 + 1*60000) / 2 = 50000
    assert money(body["avg_buy_price"]) == money("50000")
    assert money(body["value"]) == money("100000")  # 2 * 50000 (last known price, unchanged)


async def test_sell_reduces_quantity_but_not_the_average_cost_of_what_remains(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "2", "40000")  # avg cost 40000

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "1", "price_per_unit": "55000", "date": "2026-02-01"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert money(body["quantity"]) == money("1")
    assert money(body["avg_buy_price"]) == money("40000")  # unchanged by the sell
    assert money(body["value"]) == money("50000")  # 1 * 50000


async def test_selling_more_than_held_is_rejected(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "2", "price_per_unit": "55000", "date": "2026-02-01"},
    )

    assert resp.status_code == 400


async def test_deleting_a_transaction_recomputes_the_position(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")

    second = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )
    tx_id = next(
        t["id"]
        for t in (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()
        if t["price_per_unit"] == "60000.000000000000000000"
    )
    assert second.json()["quantity"] == "2.000000000000000000"

    resp = await client.delete(f"/crypto/transactions/{tx_id}")
    assert resp.status_code == 204

    refreshed = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert money(refreshed["quantity"]) == money("1")
    assert money(refreshed["avg_buy_price"]) == money("40000")


async def test_transaction_history_lists_newest_first(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000", )
    await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    resp = await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")

    assert resp.status_code == 200
    dates = [t["date"] for t in resp.json()]
    assert dates == ["2026-02-01", "2026-01-01"]


async def test_deleting_the_asset_removes_the_crypto_holding_too(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)

    resp = await client.delete(f"/assets/{holding['asset_id']}")
    assert resp.status_code == 204

    resp = await client.get("/crypto/holdings")
    assert resp.json()["holdings"] == []


async def test_get_holdings_does_not_resync_within_24_hours(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client)

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {}

    monkeypatch.setattr(crypto_service, "_fetch_market_data", counting_fetch)

    resp = await client.get("/crypto/holdings")

    assert resp.json()["synced"] is False
    assert calls == []  # creation's own sync already satisfied the 24h window


async def test_manual_refresh_button_bypasses_the_24h_window_and_updates_changes(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "0.5", "40000")

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {"bitcoin": _point("60000", change_1h="0.5", change_24h="2.1", change_7d="-3.4")}

    monkeypatch.setattr(crypto_service, "_fetch_market_data", counting_fetch)

    resp = await client.post("/crypto/refresh")

    assert resp.json()["synced"] is True
    assert calls == [["bitcoin"]]
    holding = resp.json()["holdings"][0]
    assert money(holding["value"]) == money("30000")  # 0.5 * 60000
    assert money(holding["price_change_1h"]) == money("0.5")
    assert money(holding["price_change_24h"]) == money("2.1")
    assert money(holding["price_change_7d"]) == money("-3.4")


async def test_coingecko_outage_keeps_last_known_value_instead_of_failing(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "0.5", "40000")

    async def broken_fetch(coingecko_ids, vs_currency):
        raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(crypto_service, "_fetch_market_data", broken_fetch)

    resp = await client.post("/crypto/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] is False
    assert body["error_key"] == "unreachable"
    assert money(body["holdings"][0]["value"]) == money("25000")  # unchanged from creation


async def test_create_rejects_when_no_api_key_configured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service.get_settings(), "coingecko_api_key", "")

    resp = await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "0.5",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
    )

    assert resp.status_code == 400


async def test_backup_roundtrip_preserves_holding_and_transaction_log(client: AsyncClient, monkeypatch):
    """A crypto holding is an Asset underneath, so it would still show up
    after a restore even without this — but as an inert manual asset,
    having silently lost which coin it was and its whole buy/sell history
    (so quantity and avg buy price couldn't be recomputed). Backup must
    carry both CryptoHolding and CryptoTransaction rows."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")
    await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    payload = (await client.get("/backup/export")).json()
    assert len(payload["crypto_holdings"]) == 1
    assert len(payload["crypto_transactions"]) == 2

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    restored = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert restored["coingecko_id"] == "bitcoin"
    assert restored["asset_id"] == holding["asset_id"]
    assert money(restored["quantity"]) == money("2")
    assert money(restored["avg_buy_price"]) == money("50000")
    assert money(restored["value"]) == money("100000")  # last_price survived too (2 * 50000)


async def test_backup_roundtrip_preserves_portfolio_assignment(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    portfolio = (await client.post("/crypto/portfolios", json={"name": "Long-term"})).json()
    resp = await client.post(
        "/crypto/holdings",
        json={
            "portfolio_id": portfolio["id"],
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "1",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
    )
    assert resp.status_code == 201, resp.text

    payload = (await client.get("/backup/export")).json()
    assert len(payload["crypto_portfolios"]) == 1
    assert payload["crypto_holdings"][0]["portfolio_id"] == portfolio["id"]

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    restored_portfolios = (await client.get("/crypto/portfolios")).json()
    assert len(restored_portfolios) == 1
    assert restored_portfolios[0]["name"] == "Long-term"
    restored_holding = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert restored_holding["portfolio_id"] == restored_portfolios[0]["id"]


async def test_restoring_a_pre_portfolios_backup_falls_back_to_a_default_portfolio(client: AsyncClient, monkeypatch):
    """A backup exported before crypto portfolios existed has no
    crypto_portfolios list and every holding's portfolio_id is absent —
    restore_backup() must still produce a valid NOT NULL portfolio_id
    instead of failing the import."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")

    payload = (await client.get("/backup/export")).json()
    payload["crypto_portfolios"] = []
    payload["crypto_holdings"][0]["portfolio_id"] = None

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    restored_portfolios = (await client.get("/crypto/portfolios")).json()
    assert len(restored_portfolios) == 1
    restored_holding = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert restored_holding["asset_id"] == holding["asset_id"]
    assert restored_holding["portfolio_id"] == restored_portfolios[0]["id"]


async def test_history_reflects_current_total_crypto_value(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "1", "40000")

    resp = await client.get("/crypto/history?range=30d")

    assert resp.status_code == 200
    body = resp.json()
    assert money(body["current"]) == money("50000")
    assert len(body["series"]) == 30
    assert money(body["series"][-1]["value"]) == money("50000")
    assert money(body["series"][0]["value"]) == money("0")  # nothing existed 30 days ago


async def test_history_is_empty_series_with_no_holdings(client: AsyncClient):
    resp = await client.get("/crypto/history?range=7d")

    assert resp.status_code == 200
    body = resp.json()
    assert body["series"] == []
    assert money(body["current"]) == money("0")


async def test_history_rejects_unknown_range(client: AsyncClient):
    resp = await client.get("/crypto/history?range=24h")

    assert resp.status_code == 422


async def test_update_transaction_recomputes_position_without_calling_coingecko(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")
    tx_id = (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()[0]["id"]

    async def fail_if_called(coingecko_ids, vs_currency):
        raise AssertionError("editing a transaction must not call CoinGecko")

    monkeypatch.setattr(crypto_service, "_fetch_market_data", fail_if_called)

    resp = await client.patch(f"/crypto/transactions/{tx_id}", json={"quantity": "2"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert money(body["quantity"]) == money("2")
    assert money(body["value"]) == money("100000")  # 2 * 50000 (last known price)


async def test_update_transaction_edits_are_reflected_in_history(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")
    tx_id = (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()[0]["id"]

    resp = await client.patch(
        f"/crypto/transactions/{tx_id}", json={"price_per_unit": "45000", "note": "typo fix"}
    )
    assert resp.status_code == 200, resp.text

    transactions = (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()
    assert len(transactions) == 1
    assert money(transactions[0]["price_per_unit"]) == money("45000")
    assert transactions[0]["note"] == "typo fix"


async def test_update_transaction_rejects_editing_a_sell_to_exceed_holdings(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "2", "40000")
    await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "1", "price_per_unit": "45000", "date": "2026-02-01"},
    )
    sell_tx_id = next(
        t["id"]
        for t in (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()
        if t["type"] == "sell"
    )

    resp = await client.patch(f"/crypto/transactions/{sell_tx_id}", json={"quantity": "3"})

    assert resp.status_code == 400


async def test_refresh_updates_30d_and_1y_change(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "0.5", "40000")

    async def counting_fetch(coingecko_ids, vs_currency):
        return {
            "bitcoin": crypto_service._MarketPoint(
                price=Decimal("60000"),
                change_1h=None,
                change_24h=None,
                change_7d=None,
                change_30d=Decimal("15.5"),
                change_1y=Decimal("120.25"),
            )
        }

    monkeypatch.setattr(crypto_service, "_fetch_market_data", counting_fetch)

    resp = await client.post("/crypto/refresh")

    holding = resp.json()["holdings"][0]
    assert money(holding["price_change_30d"]) == money("15.5")
    assert money(holding["price_change_1y"]) == money("120.25")


async def test_90d_performance_reflects_a_real_market_chart_fetch(client: AsyncClient, monkeypatch):
    """The 90d Best/Worst Performer window can't ride along with the regular
    sync (CoinGecko's /coins/markets has no 90d bucket) — it's a separate
    on-demand fetch, monkeypatched here at the same seam _fetch_market_data
    is patched at elsewhere in this file."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)

    # get_90d_performance checks _require_api_key() itself, separately from
    # _fetch_90d_change below — CI has no AURUM_COINGECKO_API_KEY configured
    # (unlike a local .env), so this must be stubbed too or the route 400s
    # before ever reaching the mocked fetch.
    monkeypatch.setattr(crypto_service.get_settings(), "coingecko_api_key", "test-key")

    async def fake_90d_change(client_, api_key, coingecko_id, vs_currency):
        return 12.5 if coingecko_id == "bitcoin" else None

    monkeypatch.setattr(crypto_service, "_fetch_90d_change", fake_90d_change)

    resp = await client.get("/crypto/performance/90d")

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == [{"asset_id": holding["asset_id"], "price_change_percent": 12.5}]


async def test_90d_performance_skips_fully_sold_holdings(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")
    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "1", "price_per_unit": "45000", "date": "2026-02-01"},
    )
    assert resp.status_code == 201, resp.text

    calls: list[str] = []

    async def fake_90d_change(client_, api_key, coingecko_id, vs_currency):
        calls.append(coingecko_id)
        return 5.0

    monkeypatch.setattr(crypto_service, "_fetch_90d_change", fake_90d_change)

    resp = await client.get("/crypto/performance/90d")

    assert resp.json()["items"] == []
    assert calls == []  # a coin with zero quantity has nothing to fetch a price for


async def test_90d_performance_filters_by_portfolio(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    portfolio_a = (await client.post("/crypto/portfolios", json={"name": "A"})).json()
    portfolio_b = (await client.post("/crypto/portfolios", json={"name": "B"})).json()

    async def add(portfolio_id):
        resp = await client.post(
            "/crypto/holdings",
            json={
                "portfolio_id": portfolio_id,
                "coingecko_id": "bitcoin",
                "symbol": "btc",
                "name": "Bitcoin",
                "quantity": "1",
                "price_per_unit": "40000",
                "date": "2026-01-01",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    await add(portfolio_a["id"])
    holding_b = await add(portfolio_b["id"])

    monkeypatch.setattr(crypto_service.get_settings(), "coingecko_api_key", "test-key")

    async def fake_90d_change(client_, api_key, coingecko_id, vs_currency):
        return 3.0

    monkeypatch.setattr(crypto_service, "_fetch_90d_change", fake_90d_change)

    resp = await client.get(f"/crypto/performance/90d?portfolio_id={portfolio_b['id']}")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [item["asset_id"] for item in items] == [holding_b["asset_id"]]


async def test_holdings_are_sorted_by_invested_amount_descending(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        crypto_service,
        "_fetch_market_data",
        _fake_fetch({"bitcoin": _point("50000"), "ethereum": _point("2000"), "litecoin": _point("60")}),
    )

    async def add(coingecko_id, symbol, quantity, price_per_unit):
        resp = await client.post(
            "/crypto/holdings",
            json={
                "coingecko_id": coingecko_id,
                "symbol": symbol,
                "name": symbol,
                "quantity": quantity,
                "price_per_unit": price_per_unit,
                "date": "2026-01-01",
            },
        )
        assert resp.status_code == 201, resp.text

    # Cost basis: LTC 100, BTC 5000, ETH 1000 — expect BTC, ETH, LTC.
    await add("litecoin", "ltc", "2", "50")
    await add("bitcoin", "btc", "0.1", "50000")
    await add("ethereum", "eth", "1", "1000")

    resp = await client.get("/crypto/holdings")

    symbols = [h["symbol"] for h in resp.json()["holdings"]]
    assert symbols == ["BTC", "ETH", "LTC"]


async def test_fully_sold_holding_sorts_last(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000"), "litecoin": _point("60")})
    )
    sold = await _add_bitcoin(client, "1", "40000")
    resp = await client.post(
        f"/crypto/holdings/{sold['asset_id']}/transactions",
        json={"type": "sell", "quantity": "1", "price_per_unit": "45000", "date": "2026-02-01"},
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/crypto/holdings",
        json={"coingecko_id": "litecoin", "symbol": "ltc", "name": "Litecoin", "quantity": "1", "price_per_unit": "50", "date": "2026-01-01"},
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/crypto/holdings")

    symbols = [h["symbol"] for h in resp.json()["holdings"]]
    assert symbols == ["LTC", "BTC"]  # BTC has no cost basis left (fully sold)


async def test_update_transaction_404_for_unknown_id(client: AsyncClient):
    resp = await client.patch("/crypto/transactions/999999", json={"quantity": "1"})

    assert resp.status_code == 404


async def test_holding_without_portfolio_id_lands_in_an_auto_created_default(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)

    portfolios = (await client.get("/crypto/portfolios")).json()
    assert len(portfolios) == 1
    assert portfolios[0]["name"] == "Main Portfolio"
    assert holding["portfolio_id"] == portfolios[0]["id"]


async def test_create_portfolio_and_file_a_holding_under_it(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    created = await client.post("/crypto/portfolios", json={"name": "Long-term"})
    assert created.status_code == 201, created.text
    portfolio = created.json()
    assert portfolio["name"] == "Long-term"
    assert portfolio["is_archived"] is False

    resp = await client.post(
        "/crypto/holdings",
        json={
            "portfolio_id": portfolio["id"],
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "0.5",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["portfolio_id"] == portfolio["id"]


async def test_same_coin_can_be_tracked_separately_in_two_portfolios(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    memes = (await client.post("/crypto/portfolios", json={"name": "Memes"})).json()
    longterm = (await client.post("/crypto/portfolios", json={"name": "Long-term"})).json()

    async def add(portfolio_id, quantity):
        resp = await client.post(
            "/crypto/holdings",
            json={
                "portfolio_id": portfolio_id,
                "coingecko_id": "bitcoin",
                "symbol": "btc",
                "name": "Bitcoin",
                "quantity": quantity,
                "price_per_unit": "40000",
                "date": "2026-01-01",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    await add(memes["id"], "1")
    await add(longterm["id"], "2")

    all_holdings = (await client.get("/crypto/holdings")).json()["holdings"]
    assert len(all_holdings) == 2

    memes_holdings = (await client.get(f"/crypto/holdings?portfolio_id={memes['id']}")).json()["holdings"]
    assert len(memes_holdings) == 1
    assert money(memes_holdings[0]["quantity"]) == money("1")

    longterm_history = (await client.get(f"/crypto/history?range=30d&portfolio_id={longterm['id']}")).json()
    assert money(longterm_history["current"]) == money("100000")  # 2 * 50000, memes' 1 BTC excluded


async def test_deleting_a_nonempty_portfolio_is_rejected(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)
    portfolio_id = holding["portfolio_id"]

    resp = await client.delete(f"/crypto/portfolios/{portfolio_id}")

    assert resp.status_code == 400


async def test_archived_portfolios_are_excluded_by_default(client: AsyncClient):
    portfolio = (await client.post("/crypto/portfolios", json={"name": "Old fund"})).json()

    await client.patch(f"/crypto/portfolios/{portfolio['id']}", json={"is_archived": True})

    visible = (await client.get("/crypto/portfolios")).json()
    assert visible == []

    with_archived = (await client.get("/crypto/portfolios?include_archived=true")).json()
    assert len(with_archived) == 1
    assert with_archived[0]["is_archived"] is True


async def test_empty_archived_portfolio_can_be_deleted(client: AsyncClient):
    portfolio = (await client.post("/crypto/portfolios", json={"name": "Unused"})).json()

    resp = await client.delete(f"/crypto/portfolios/{portfolio['id']}")

    assert resp.status_code == 204
    assert (await client.get("/crypto/portfolios")).json() == []


async def test_create_holding_defaults_risk_level_to_high(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client)

    assert holding["risk_level"] == "high"


async def test_create_holding_accepts_a_custom_risk_level(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client, risk_level="low")

    assert holding["risk_level"] == "low"


async def test_holding_risk_level_is_editable_via_the_underlying_asset(client: AsyncClient, monkeypatch):
    """risk_level lives on the Asset, not CryptoHolding — see
    services/crypto_service.py's _to_read — so it's edited through the
    existing PATCH /assets/{asset_id}, same endpoint every other Asset
    already uses, rather than a crypto-specific route."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, risk_level="high")

    resp = await client.patch(f"/assets/{holding['asset_id']}", json={"risk_level": "medium"})
    assert resp.status_code == 200, resp.text

    refreshed = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert refreshed["risk_level"] == "medium"


async def test_create_holding_defaults_network_to_null(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client)

    assert holding["network"] is None


async def test_create_holding_accepts_a_network(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client, network="Ethereum")

    assert holding["network"] == "Ethereum"


async def test_update_holding_network(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)

    resp = await client.patch(f"/crypto/holdings/{holding['asset_id']}", json={"network": "Tron"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["network"] == "Tron"
    refreshed = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert refreshed["network"] == "Tron"


async def test_update_holding_network_can_be_cleared_with_null(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, network="Ethereum")

    resp = await client.patch(f"/crypto/holdings/{holding['asset_id']}", json={"network": None})

    assert resp.status_code == 200, resp.text
    assert resp.json()["network"] is None


async def test_update_holding_omitting_network_leaves_it_untouched(client: AsyncClient, monkeypatch):
    """Partial PATCH semantics, same as every other endpoint in this app —
    an empty body must not silently null out a field the caller didn't
    mention (see schemas/crypto.py's CryptoHoldingUpdate)."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, network="Ethereum")

    resp = await client.patch(f"/crypto/holdings/{holding['asset_id']}", json={})

    assert resp.status_code == 200, resp.text
    assert resp.json()["network"] == "Ethereum"


async def test_update_holding_404_for_unknown_id(client: AsyncClient):
    resp = await client.patch("/crypto/holdings/999999", json={"network": "Ethereum"})

    assert resp.status_code == 404
