"""Tool behavior tests: request shapes, response compaction, write registry."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from aurum_agent.tools import build_tools

# Every tool that mutates data — the confirmation router's source of truth.
EXPECTED_WRITE_NAMES = {
    "create_account",
    "update_account",
    "delete_account",
    "create_category",
    "update_category",
    "delete_category",
    "create_tag",
    "create_transaction",
    "update_transaction",
    "delete_transaction",
}


def bundle_by_name(bundle: Any) -> dict[str, Any]:
    return {tool.name: tool for tool in bundle.tools}


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def account_payload() -> list[dict[str, Any]]:
    # Extra fields on purpose: compaction must drop them.
    return [
        {
            "id": 1,
            "name": "Checking",
            "type": "checking",
            "currency": "USD",
            "color": "#4f46e5",
            "is_archived": False,
            "balance": "1523.40",
        }
    ]


def transaction_payload() -> dict[str, Any]:
    # Nested account/category/tags on purpose: compaction must flatten
    # them to the *_name fields the model speaks in.
    return {
        "id": 7,
        "account_id": 1,
        "account": {"id": 1, "name": "Cash", "type": "cash", "currency": "USD", "color": None},
        "category_id": 4,
        "category": {"id": 4, "name": "Groceries", "kind": "expense", "color": "#22c55e"},
        "transfer_account_id": None,
        "type": "expense",
        "amount": "42.50",
        "description": "Groceries",
        "merchant": "Whole Foods",
        "notes": None,
        "date": "2026-11-21",
        "tags": [{"id": 3, "name": "weekend"}],
        "splits": [],
    }


async def test_write_names_registry_is_exact(
    mock_client_factory: Any,
) -> None:
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    bundle = build_tools(client)
    by_name = bundle_by_name(bundle)

    assert bundle.write_names == EXPECTED_WRITE_NAMES
    # A write name without a matching tool would break the router's trust.
    assert bundle.write_names <= set(by_name)


async def test_list_accounts_compacts_to_model_fields(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=account_payload()))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["list_accounts"].ainvoke({})

    assert json.loads(result) == [
        {
            "id": 1,
            "name": "Checking",
            "type": "checking",
            "currency": "USD",
            "balance": "1523.40",
            "is_archived": False,
        }
    ]
    assert str(calls[0].url) == "http://test.local/api/accounts"
    # Archived accounts stay hidden without the explicit opt-in.
    assert "include_archived" not in calls[0].url.params


async def test_list_accounts_include_archived_param(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["list_accounts"].ainvoke({"include_archived": True})

    assert calls[0].url.params["include_archived"] == "true"


async def test_create_account_omits_unset_optionals(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(201, json=account_payload()[0])
    )
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["create_account"].ainvoke({"name": "Cash"})

    assert calls[0].method == "POST"
    assert body_of(calls[0]) == {"name": "Cash"}
    # The created object comes back compacted, not raw.
    assert json.loads(result)["name"] == "Checking"


async def test_update_account_sends_only_provided_fields(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=account_payload()[0])
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_account"].ainvoke(
        {"account_id": 3, "name": "Wallet", "is_archived": True}
    )

    assert calls[0].method == "PATCH"
    assert str(calls[0].url) == "http://test.local/api/accounts/3"
    # is_archived=true travels with the rename; nothing else does.
    assert body_of(calls[0]) == {"name": "Wallet", "is_archived": True}


async def test_update_account_false_is_kept_not_dropped(mock_client_factory: Any) -> None:
    # False is a real value (unarchive), not "leave unchanged".
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=account_payload()[0])
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_account"].ainvoke(
        {"account_id": 3, "is_archived": False}
    )

    assert body_of(calls[0]) == {"is_archived": False}


async def test_update_account_without_fields_makes_no_call(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json={}))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["update_account"].ainvoke({"account_id": 3})

    assert calls == []  # a no-op request would only confuse the backend
    assert "Нечего обновлять" in result


async def test_delete_account_reports_204_without_body(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(204))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["delete_account"].ainvoke({"account_id": 5})

    assert calls[0].method == "DELETE"
    assert str(calls[0].url) == "http://test.local/api/accounts/5"
    assert "204" in result


async def test_list_categories_filters_by_kind(mock_client_factory: Any) -> None:
    payload = [
        {"id": 4, "name": "Groceries", "kind": "expense", "icon": "cart", "color": "#22c55e",
         "sort_order": 0, "parent_id": None, "is_default": True}
    ]
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=payload))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["list_categories"].ainvoke({"kind": "expense"})

    assert calls[0].url.params["kind"] == "expense"
    assert json.loads(result) == [
        {"id": 4, "name": "Groceries", "kind": "expense", "parent_id": None, "is_default": True}
    ]


async def test_update_category_clear_parent_sends_explicit_null(
    mock_client_factory: Any,
) -> None:
    payload = {"id": 9, "name": "Sweets", "kind": "expense", "parent_id": None, "is_default": False}
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=payload))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_category"].ainvoke(
        {"category_id": 9, "clear_parent": True}
    )

    # Omitted parent_id keeps the parent; explicit null detaches — two
    # different requests per DOCS.md, so the flag must produce null.
    assert body_of(calls[0]) == {"parent_id": None}


async def test_update_category_parent_value_passes_through(mock_client_factory: Any) -> None:
    payload = {"id": 9, "name": "Sweets", "kind": "expense", "parent_id": 4, "is_default": False}
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=payload))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_category"].ainvoke(
        {"category_id": 9, "parent_id": 4}
    )

    assert body_of(calls[0]) == {"parent_id": 4}


async def test_create_tag_posts_name(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(201, json={"id": 2, "name": "Vacation"})
    )
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["create_tag"].ainvoke({"name": "Vacation"})

    assert calls[0].method == "POST"
    assert body_of(calls[0]) == {"name": "Vacation"}
    assert json.loads(result) == {"id": 2, "name": "Vacation"}


async def test_api_error_becomes_tool_text_not_exception(mock_client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Category 'Salary' is a income category"})

    client, _ = mock_client_factory(handler)
    bundle = build_tools(client)

    # The model must see the backend's own message to self-correct.
    result = await bundle_by_name(bundle)["create_tag"].ainvoke({"name": "x"})

    assert "Ошибка API (код 400)" in result
    assert "income category" in result


async def test_validation_error_list_reaches_tool_text(mock_client_factory: Any) -> None:
    # 422 bodies carry a per-field list; the model needs it field-named.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": [{"loc": ["body", "name"], "msg": "Field required", "type": "missing"}]},
        )

    client, _ = mock_client_factory(handler)
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["create_category"].ainvoke(
        {"name": "x", "kind": "expense", "color": "#22c55e"}
    )

    assert "Ошибка API (код 422)" in result
    assert "name: Field required" in result


async def test_transport_failure_reaches_tool_text(mock_client_factory: Any) -> None:
    # The stack being down must read as an actionable tool result, not
    # as an exception the graph has to catch.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client, _ = mock_client_factory(handler)
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["list_accounts"].ainvoke({})

    assert "Ошибка API (код 0)" in result
    assert "Не удалось соединиться" in result


async def test_get_transaction_flattens_nested_names(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=transaction_payload())
    )
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["get_transaction"].ainvoke({"transaction_id": 7})

    assert str(calls[0].url) == "http://test.local/api/transactions/7"
    parsed = json.loads(result)
    assert parsed["account_name"] == "Cash"
    assert parsed["category_name"] == "Groceries"
    assert parsed["tags"] == ["weekend"]
    assert parsed["splits"] == []


async def test_get_transaction_compacts_splits(mock_client_factory: Any) -> None:
    payload = transaction_payload()
    payload["splits"] = [
        {
            "id": 1,
            "category_id": 12,
            "category": {"id": 12, "name": "Sweets", "kind": "expense", "color": "#f97316"},
            "amount": "60.00",
            "note": "Sweets",
        }
    ]
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=payload))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["get_transaction"].ainvoke({"transaction_id": 7})

    # The split branch: nested category flattened, amount stays a string
    # Decimal, note passes through.
    assert json.loads(result)["splits"] == [
        {"category_name": "Sweets", "amount": "60.00", "note": "Sweets"}
    ]


async def test_search_transactions_builds_filters_and_keeps_pager(
    mock_client_factory: Any,
) -> None:
    page_payload = {
        "items": [transaction_payload()],
        "total": 43,
        "page": 2,
        "page_size": 20,
    }
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=page_payload))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["search_transactions"].ainvoke(
        {
            "year": 2026,
            "month": 11,
            "account_id": 1,
            "type": "expense",
            "search": "coffee",
            "sort": "amount_desc",
            "page": 2,
        }
    )

    params = calls[0].url.params
    assert params["year"] == "2026"
    assert params["month"] == "11"
    assert params["account_id"] == "1"
    assert params["type"] == "expense"
    assert params["search"] == "coffee"
    assert params["sort"] == "amount_desc"
    assert params["page"] == "2"
    parsed = json.loads(result)
    # The pager fields tell the model whether more pages exist.
    assert parsed["total"] == 43
    assert parsed["page"] == 2
    assert parsed["page_size"] == 20
    assert parsed["items"][0]["description"] == "Groceries"


async def test_search_transactions_drops_unset_filters(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json={"items": [], "total": 0}))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["search_transactions"].ainvoke({})

    # Only the defaults travel; no "None" strings leak into the query.
    assert dict(calls[0].url.params) == {"page": "1", "page_size": "20"}


async def test_search_transactions_drops_blank_string_filters(
    mock_client_factory: Any,
) -> None:
    # "" or whitespace-only would fail backend validation — treat as unset.
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json={"items": [], "total": 0}))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["search_transactions"].ainvoke(
        {"search": "   ", "start_date": "", "end_date": " "}
    )

    assert dict(calls[0].url.params) == {"page": "1", "page_size": "20"}


async def test_search_transactions_date_range_and_id_filters(
    mock_client_factory: Any,
) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json={"items": [], "total": 0}))
    bundle = build_tools(client)

    await bundle_by_name(bundle)["search_transactions"].ainvoke(
        {
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "category_id": 4,
            "tag_id": 3,
        }
    )

    params = dict(calls[0].url.params)
    assert params["start_date"] == "2026-11-01"
    assert params["end_date"] == "2026-11-30"
    assert params["category_id"] == "4"
    assert params["tag_id"] == "3"


async def test_create_transaction_income_body(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(201, json=transaction_payload())
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["create_transaction"].ainvoke(
        {
            "account_id": 1,
            "type": "expense",
            "amount": 42.5,
            "description": "Groceries",
            "date": "2026-11-21",
            "category_id": 4,
            "tag_ids": [3],
        }
    )

    assert calls[0].method == "POST"
    assert body_of(calls[0]) == {
        "account_id": 1,
        "type": "expense",
        "amount": 42.5,
        "description": "Groceries",
        "date": "2026-11-21",
        "category_id": 4,
        "tag_ids": [3],
    }


async def test_create_transaction_transfer_omits_category(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(201, json=transaction_payload())
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["create_transaction"].ainvoke(
        {
            "account_id": 1,
            "type": "transfer",
            "amount": 100.0,
            "description": "Move to savings",
            "date": "2026-11-21",
            "transfer_account_id": 2,
        }
    )

    # A transfer must not carry a category — omitted, not null.
    assert body_of(calls[0]) == {
        "account_id": 1,
        "type": "transfer",
        "amount": 100.0,
        "description": "Move to savings",
        "date": "2026-11-21",
        "transfer_account_id": 2,
    }


async def test_update_transaction_clear_flags_send_nulls(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=transaction_payload())
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_transaction"].ainvoke(
        {"transaction_id": 7, "type": "expense", "clear_category": True, "clear_transfer": True}
    )

    # The backend's exclude_unset treats null as "clear", omit as "keep";
    # the flags must produce the nulls.
    assert body_of(calls[0]) == {
        "type": "expense",
        "category_id": None,
        "transfer_account_id": None,
    }


async def test_update_transaction_clear_flags_win_over_ids(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=transaction_payload())
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_transaction"].ainvoke(
        {"transaction_id": 7, "category_id": 5, "clear_category": True}
    )

    assert body_of(calls[0]) == {"category_id": None}


async def test_update_transaction_empty_tag_list_replaces_set(mock_client_factory: Any) -> None:
    # An empty list is a real value ("remove all tags"), not "unset" —
    # _omit_none must keep it.
    client, calls = mock_client_factory(
        lambda request: httpx.Response(200, json=transaction_payload())
    )
    bundle = build_tools(client)

    await bundle_by_name(bundle)["update_transaction"].ainvoke(
        {"transaction_id": 7, "tag_ids": []}
    )

    assert body_of(calls[0]) == {"tag_ids": []}


async def test_delete_transaction_path_and_204(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(204))
    bundle = build_tools(client)

    result = await bundle_by_name(bundle)["delete_transaction"].ainvoke({"transaction_id": 9})

    assert calls[0].method == "DELETE"
    assert str(calls[0].url) == "http://test.local/api/transactions/9"
    assert "204" in result


@pytest.mark.parametrize(
    ("tool_name", "is_write"),
    [
        ("list_accounts", False),
        ("create_account", True),
        ("update_account", True),
        ("delete_account", True),
        ("list_categories", False),
        ("create_category", True),
        ("update_category", True),
        ("delete_category", True),
        ("list_tags", False),
        ("create_tag", True),
        ("get_transaction", False),
        ("search_transactions", False),
        ("create_transaction", True),
        ("update_transaction", True),
        ("delete_transaction", True),
    ],
)
async def test_every_tool_is_classified(
    mock_client_factory: Any, tool_name: str, is_write: bool
) -> None:
    # Pins the read/write split for each tool — the router depends on it.
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    bundle = build_tools(client)
    assert (tool_name in bundle.write_names) is is_write
    assert tool_name in bundle_by_name(bundle)
