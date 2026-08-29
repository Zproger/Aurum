"""Savings goals: contribution rules.

The contribution log accepts negative amounts on purpose (taking money back
out of a goal is still an entry in its running total), which is exactly why
zero has to be rejected explicitly rather than by a `gt=0` constraint.
"""
from httpx import AsyncClient

from tests.helpers import money


async def _goal(client: AsyncClient) -> dict:
    return (await client.post("/goals", json={"name": "Emergency fund", "target_amount": "1000"})).json()


async def test_zero_contribution_is_rejected(client: AsyncClient):
    goal = await _goal(client)

    resp = await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "0", "date": "2026-01-15"})

    assert resp.status_code == 422
    assert money((await client.get("/goals")).json()[0]["current_amount"]) == money(0)


async def test_negative_contribution_is_allowed(client: AsyncClient):
    """Withdrawing from a goal is a legitimate entry — the zero check must not
    turn into a positive-only constraint."""
    goal = await _goal(client)
    await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "250", "date": "2026-01-15"})

    resp = await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "-100", "date": "2026-02-01"})

    assert resp.status_code == 201
    assert money(resp.json()["current_amount"]) == money("150")
