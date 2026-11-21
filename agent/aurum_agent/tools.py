"""LangChain tools over the Aurum REST API: accounts, categories, tags.

Each tool is a thin, typed wrapper around one endpoint: it compacts the
response into model-friendly JSON, or turns an ``AurumApiError`` into a
plain-text error string the model can read and react to. The tools
themselves know nothing about confirmations — that is the graph's job
(see graph.py): any name in ``ToolBundle.write_names`` is routed through
a terminal "yes" before its REST call is allowed to run.

Scope notes: transaction splits are deliberately not exposed in this
MVP, and neither is ``DELETE /tags/{id}`` — tags are only created and
listed here, because the block-1 agent helps tag transactions, not
manage the tag dictionary itself.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from .api_client import AurumApiError, AurumClient

# REST endpoints in one place, matching DOCS.md. Dynamic segments are
# appended at call sites: f"{PATH_ACCOUNTS}/{account_id}".
PATH_ACCOUNTS = "/accounts"
PATH_CATEGORIES = "/categories"
PATH_TAGS = "/tags"


@dataclass(frozen=True)
class ToolBundle:
    """The agent's toolset plus the names that mutate data.

    ``write_names`` is the source of truth for the confirmation router —
    filled in right next to each tool definition and pinned by tests,
    so the registry and the router stay in lockstep.
    """

    tools: list[BaseTool]
    write_names: frozenset[str]


def _dumps(value: Any) -> str:
    """JSON for the model's eyes: readable separators, real unicode."""
    return json.dumps(value, ensure_ascii=False)


def _omit_none(**fields: Any) -> dict[str, Any]:
    """Keep only provided fields — ``None`` means "leave unchanged".

    ``False`` is a real value (e.g. ``is_archived=false`` restores an
    archived account), so only ``None`` is dropped.
    """
    return {name: value for name, value in fields.items() if value is not None}


def _make_caller(client: AurumClient) -> Callable[..., Awaitable[str]]:
    """One HTTP call per tool: errors become text the model can act on."""

    async def call(
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        compact: Callable[[Any], Any] | None = None,
    ) -> str:
        # Centralized PATCH guard: an empty partial-update body is always
        # a modeling mistake, and the backend would reject it with a less
        # helpful message than this. Lives here so every update tool —
        # including the transaction ones added later — gets it for free.
        if method == "PATCH" and body is not None and not body:
            return "Нечего обновлять: передайте хотя бы одно изменяемое поле."
        try:
            payload = await client.request(method, path, params=params, json=body)
        except AurumApiError as error:
            # Not re-raised on purpose: as a tool result, the backend's
            # own message (e.g. "Category 'Salary' is a income category…")
            # lets the model correct itself on the next step.
            return f"Ошибка API (код {error.status}): {error.detail}"
        if compact is not None:
            payload = compact(payload)
        if payload is None:
            # Deletes answer 204 with no body — "null" would only confuse.
            return "OK: выполнено (204 No Content)"
        return _dumps(payload)

    return call


def _compact_account(account: dict[str, Any]) -> dict[str, Any]:
    """Fields the model needs to pick an account; balance is derived."""
    return {
        "id": account.get("id"),
        "name": account.get("name"),
        "type": account.get("type"),
        "currency": account.get("currency"),
        "balance": account.get("balance"),
        "is_archived": account.get("is_archived"),
    }


def _compact_category(category: dict[str, Any]) -> dict[str, Any]:
    """Fields the model needs to pick or build a category."""
    return {
        "id": category.get("id"),
        "name": category.get("name"),
        "kind": category.get("kind"),
        "parent_id": category.get("parent_id"),
        "is_default": category.get("is_default"),
    }


def _tool(func: Callable[..., Awaitable[str]], description: str) -> BaseTool:
    """Wrap a typed async function into a LangChain tool.

    The async callable must go via ``coroutine=`` — passing it as the
    positional ``func`` makes langchain-core 1.x treat it as sync and
    return an un-awaited coroutine object. The args schema is inferred
    from the signature and annotations, so what the model sees matches
    exactly what the code enforces.
    """
    return StructuredTool.from_function(coroutine=func, description=description)


class _Registry:
    """Tool registration with an explicit read/write class per tool.

    Every tool is declared through ``@registry.add(..., is_write=...)`` —
    reads carry the explicit default too — so the confirmation split is
    visible at each definition instead of being implied by an absent
    ``writes.add`` line somewhere above it.
    """

    def __init__(self) -> None:
        self._tools: list[BaseTool] = []
        self._write_names: set[str] = set()

    def add(
        self,
        description: str,
        *,
        is_write: bool = False,
    ) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
        """Decorator: register the wrapped async function as a tool."""

        def decorator(func: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
            self._tools.append(_tool(func, description))
            if is_write:
                self._write_names.add(func.__name__)
            return func

        return decorator

    def bundle(self) -> ToolBundle:
        return ToolBundle(
            tools=list(self._tools),
            write_names=frozenset(self._write_names),
        )


def build_tools(client: AurumClient) -> ToolBundle:
    """Build the toolset bound to one API client instance."""
    call = _make_caller(client)
    registry = _Registry()

    # --- Accounts ---

    @registry.add(
        "List the user's accounts with live balances, one JSON object per "
        "account (id, name, type, currency, balance, is_archived). Archived "
        "accounts are hidden unless include_archived=true."
    )
    async def list_accounts(include_archived: bool = False) -> str:
        params = {"include_archived": "true"} if include_archived else None
        return await call(
            "GET",
            PATH_ACCOUNTS,
            params=params,
            compact=lambda items: [_compact_account(item) for item in items],
        )

    @registry.add(
        "Create a new account — a bank account, card, or cash wallet. "
        "name is required (1-100 chars). type: checking | debit_card | "
        "savings | credit_card | cash | investment | other (default "
        "checking). currency: 3-letter display code, default USD. "
        "color: 6-digit hex like '#4f46e5'.",
        is_write=True,
    )
    async def create_account(
        name: str,
        type: str | None = None,
        currency: str | None = None,
        color: str | None = None,
    ) -> str:
        body = _omit_none(name=name, type=type, currency=currency, color=color)
        return await call("POST", PATH_ACCOUNTS, body=body, compact=_compact_account)

    @registry.add(
        "Update an account partially — only the fields you pass change, "
        "omitted ones stay as-is. Use is_archived=true to hide an account "
        "without deleting it; is_archived=false restores it.",
        is_write=True,
    )
    async def update_account(
        account_id: int,
        name: str | None = None,
        type: str | None = None,
        currency: str | None = None,
        color: str | None = None,
        is_archived: bool | None = None,
    ) -> str:
        body = _omit_none(
            name=name,
            type=type,
            currency=currency,
            color=color,
            is_archived=is_archived,
        )
        return await call(
            "PATCH",
            f"{PATH_ACCOUNTS}/{account_id}",
            body=body,
            compact=_compact_account,
        )

    @registry.add(
        "PERMANENTLY delete an account and EVERY transaction on it — "
        "irreversible. The most destructive call in this toolset: prefer "
        "update_account with is_archived=true unless the user explicitly "
        "insists on deletion.",
        is_write=True,
    )
    async def delete_account(account_id: int) -> str:
        return await call("DELETE", f"{PATH_ACCOUNTS}/{account_id}")

    # --- Categories ---

    @registry.add(
        "List categories sorted by display order (id, name, kind, "
        "parent_id, is_default). kind: 'expense' or 'income' filters to "
        "one side; omit for both. Subcategories carry the parent_id of a "
        "top-level category of the same kind."
    )
    async def list_categories(kind: str | None = None) -> str:
        params = {"kind": kind} if kind else None
        return await call(
            "GET",
            PATH_CATEGORIES,
            params=params,
            compact=lambda items: [_compact_category(item) for item in items],
        )

    @registry.add(
        "Create a category or subcategory. kind: 'expense' or 'income' — "
        "required and fixed forever. name: 1-100 chars. color: required "
        "6-digit hex like '#22c55e'. parent_id: set only for a "
        "subcategory; the parent must be top-level and share the child's "
        "kind. sort_order controls display order (default 0).",
        is_write=True,
    )
    async def create_category(
        name: str,
        kind: str,
        color: str,
        icon: str | None = None,
        sort_order: int | None = None,
        parent_id: int | None = None,
    ) -> str:
        body = _omit_none(
            name=name,
            kind=kind,
            color=color,
            icon=icon,
            sort_order=sort_order,
            parent_id=parent_id,
        )
        return await call("POST", PATH_CATEGORIES, body=body, compact=_compact_category)

    @registry.add(
        "Update a category partially — omitted fields stay as-is. kind "
        "cannot be changed, ever. parent_id moves the category under a "
        "top-level parent of the same kind; clear_parent=true turns it "
        "back into a top-level category (sends parent_id=null) and wins "
        "if parent_id is also given. A category that has subcategories "
        "cannot become a subcategory.",
        is_write=True,
    )
    async def update_category(
        category_id: int,
        name: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        sort_order: int | None = None,
        parent_id: int | None = None,
        clear_parent: bool = False,
    ) -> str:
        body = _omit_none(
            name=name,
            color=color,
            icon=icon,
            sort_order=sort_order,
            parent_id=parent_id,
        )
        # Omitted parent_id keeps the current parent; explicit null clears
        # it (see DOCS.md "Partial updates") — needs its own flag, since
        # "not provided" and "set to null" are different requests.
        if clear_parent:
            body["parent_id"] = None
        return await call(
            "PATCH",
            f"{PATH_CATEGORIES}/{category_id}",
            body=body,
            compact=_compact_category,
        )

    @registry.add(
        "Delete a category. Seeded defaults (is_default=true) can only be "
        "deleted while nothing references them — the API returns 400 "
        "otherwise, with a message naming what still points at it. "
        "Deleting a custom category that has transactions leaves those "
        "transactions uncategorized (existing ones are not deleted).",
        is_write=True,
    )
    async def delete_category(category_id: int) -> str:
        return await call("DELETE", f"{PATH_CATEGORIES}/{category_id}")

    # --- Tags ---

    @registry.add("List all tags alphabetically (id, name).")
    async def list_tags() -> str:
        return await call("GET", PATH_TAGS)

    @registry.add(
        "Create a tag (1-50 chars), or return the existing one on a "
        "case-insensitive match — safe to call when unsure whether the "
        "tag already exists.",
        is_write=True,
    )
    async def create_tag(name: str) -> str:
        return await call("POST", PATH_TAGS, body={"name": name})

    return registry.bundle()
