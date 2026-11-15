"""The bot shows seeded English names in Russian and keeps user-typed names as is."""
from datetime import UTC, datetime
from decimal import Decimal
import json

import httpx
import pytest

from app import telegram_bot
from app.models.workspace import Workspace, WorkspaceKind
from app.schemas.dashboard import BalanceSummary, CategoryBreakdownItem, DashboardSummary
from app.telegram_labels import (
    DEFAULT_CATEGORY_LABELS,
    PERSONAL_WORKSPACE_LABEL,
    category_label,
    workspace_label,
)
from app.db.seed import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES
from app.telegram_widget import summary_chat_data, summary_text


def test_every_seeded_category_has_a_russian_label():
    seeded = [name for name, _icon, _color in DEFAULT_EXPENSE_CATEGORIES + DEFAULT_INCOME_CATEGORIES]
    assert [name for name in seeded if name not in DEFAULT_CATEGORY_LABELS] == []


def test_category_label_translates_defaults_and_keeps_custom_names():
    assert category_label("Dining Out") == "Кафе и рестораны"
    assert category_label("Other") == "Прочее"
    assert category_label("Кофе навынос") == "Кофе навынос"


def test_workspace_label():
    generated = Workspace(kind=WorkspaceKind.PERSONAL, display_name="Vadim's private workspace")
    renamed = Workspace(kind=WorkspaceKind.PERSONAL, display_name="Мои деньги")
    family = Workspace(kind=WorkspaceKind.HOUSEHOLD, display_name="Семья")
    assert workspace_label(generated) == PERSONAL_WORKSPACE_LABEL
    assert workspace_label(renamed) == "Мои деньги"
    assert workspace_label(family) == "Семья"


def _summary() -> DashboardSummary:
    return DashboardSummary(
        year=2026, month=11, reporting_currency="KZT",
        real_income=Decimal("100"), spent=Decimal("50"), net=Decimal("50"), transferred_out=None,
        spending_by_category=[
            CategoryBreakdownItem(category_id=1, name="Dining Out", color="#eb6834", icon=None,
                                  amount=Decimal("30"), percent=60.0),
            CategoryBreakdownItem(category_id=2, name="Кофе", color="#000000", icon=None,
                                  amount=Decimal("20"), percent=40.0),
        ],
        balance=BalanceSummary(reporting_currency="KZT", total=Decimal("10"), incomplete=False, items=[]),
    )


def test_summary_shows_translated_category_names():
    data = json.loads(summary_chat_data(_summary(), "Личное пространство", datetime.now(UTC)))
    assert [item[0] for item in data["k"]] == ["Кафе и рестораны", "Кофе"]
    text = summary_text(_summary(), "Личное пространство")
    assert "Кафе и рестораны" in text and "Dining Out" not in text


def _bot_with(handler) -> tuple[telegram_bot.TelegramBot, httpx.AsyncClient]:
    bot = object.__new__(telegram_bot.TelegramBot)
    bot.base_url = "https://api.telegram.org/bot123:SECRET"
    return bot, httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_api_error_carries_telegram_description_without_token():
    bot, client = _bot_with(lambda request: httpx.Response(
        400, json={"ok": False, "error_code": 400, "description": "Bad Request: method not found"},
    ))
    async with client:
        with pytest.raises(telegram_bot.TelegramApiError) as caught:
            await bot.api(client, "sendWidget", {"chat_id": 1})
    message = str(caught.value)
    assert "sendWidget" in message and "Bad Request: method not found" in message
    assert "SECRET" not in message and "api.telegram.org" not in message


async def test_api_error_on_non_json_response():
    bot, client = _bot_with(lambda request: httpx.Response(502, text="<html>Bad gateway</html>"))
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            await bot.api(client, "getUpdates", {})


async def test_api_returns_body_on_success():
    bot, client = _bot_with(lambda request: httpx.Response(200, json={"ok": True, "result": []}))
    async with client:
        assert await bot.api(client, "getUpdates", {}) == {"ok": True, "result": []}
