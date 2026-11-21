"""Duplicate detection before a transaction is created.

The Aurum API has no idempotency keys, so accidental doubles — a
repeated user command, a model retry — are the main hazard of the
create path. Before a ``create_transaction`` call is confirmed in the
terminal, the graph asks this module whether a "same" transaction
already exists: same date, same amount, same description
(case-insensitive). The check is advisory only — it never blocks a
creation, it just puts any match in front of the user's "yes".
"""

from __future__ import annotations

from typing import Any

from .api_client import AurumApiError, AurumClient
from .tools import PATH_TRANSACTIONS

# Same-date, same-description matches rarely exceed a page; the point
# is to catch accidental doubles, not to audit history.
DUPLICATE_PAGE_SIZE = 50


def _normalize_amount(amount: Any) -> str | None:
    """Canonical cent-level form, or None when the value is garbage.

    Tool-call args arrive from the model as ad-hoc JSON ("42,50" or
    null must not crash the check); the API answers with string
    Decimals. ``None`` lets the caller skip the row instead of dying.
    """
    try:
        return f"{float(amount):.2f}"
    except (TypeError, ValueError):
        return None


def _compact_duplicate(item: dict[str, Any]) -> dict[str, Any]:
    """What the confirmation preview shows about a likely duplicate."""
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "amount": item.get("amount"),
        "date": item.get("date"),
        "description": item.get("description"),
        "account_name": (item.get("account") or {}).get("name"),
        "category_name": (item.get("category") or {}).get("name"),
    }


async def find_duplicates(
    client: AurumClient,
    *,
    date: str,
    amount: float | str,
    description: str,
) -> list[dict[str, Any]]:
    """Find transactions that look like the one about to be created.

    The API-side ``search`` filter matches a substring over
    description/merchant/notes, so its results are a superset; the exact
    match (amount equal, description equal ignoring case and whitespace)
    is applied locally. The check is advisory and total: raw tool-call
    arguments, transport failures, API errors and odd response bodies
    all degrade to "no matches" — a failing duplicate check must never
    block the user's confirmation, the preview simply loses its
    warning line.
    """
    # Raw model output: anything non-string-ish or blank is treated as
    # "no description to match on" rather than crashing or forcing a
    # pointless 422 round trip to the backend.
    normalized_description = str(description or "").strip()
    if not normalized_description:
        return []

    wanted_amount = _normalize_amount(amount)
    if wanted_amount is None:
        return []

    params = {
        "start_date": str(date or ""),
        "end_date": str(date or ""),
        "search": normalized_description,
        "page": 1,
        "page_size": DUPLICATE_PAGE_SIZE,
    }
    try:
        payload = await client.request("GET", PATH_TRANSACTIONS, params=params)
    except AurumApiError:
        return []

    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []

    wanted_description = normalized_description.casefold()

    duplicates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_amount = _normalize_amount(item.get("amount"))
        if item_amount is None or item_amount != wanted_amount:
            continue
        item_description = str(item.get("description") or "").strip().casefold()
        if item_description != wanted_description:
            continue
        duplicates.append(_compact_duplicate(item))
    return duplicates
