"""The /summary widget: figures travel only in chat_data, which Telegram caps at
1024 bytes, and the static HTML must fit the Bot API size limits."""
from datetime import UTC, datetime
from decimal import Decimal
import json
import zlib

import pytest

from app.schemas.dashboard import BalanceSummary, CategoryBreakdownItem, DashboardSummary
from app.telegram_widget import (
    CHAT_DATA_LIMIT,
    SUMMARY_WIDGET_HTML,
    format_amount,
    summary_caption,
    summary_chat_data,
    summary_text,
)

NOW = datetime(2026, 11, 15, 12, 30, tzinfo=UTC)


def _category(name="Продукты", amount=Decimal("12500"), percent=42.4, color="#ff8800") -> CategoryBreakdownItem:
    return CategoryBreakdownItem(category_id=1, name=name, color=color, icon=None, amount=amount, percent=percent)


def _summary(
    *,
    categories=None,
    income=Decimal("500000"),
    spent=Decimal("123456.78"),
    net=Decimal("376543.22"),
    balance=Decimal("1234567.5"),
    incomplete=False,
    balance_incomplete=False,
) -> DashboardSummary:
    return DashboardSummary(
        year=2026,
        month=11,
        reporting_currency="KZT",
        incomplete=incomplete,
        real_income=income,
        spent=spent,
        net=net,
        transferred_out=Decimal("0"),
        spending_by_category=[_category()] if categories is None else categories,
        balance=BalanceSummary(reporting_currency="KZT", total=balance, incomplete=balance_incomplete, items=[]),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1234567.5"), "1 234 567.50"),
        (Decimal("1000"), "1 000"),
        (Decimal("1000.00"), "1 000"),
        (Decimal("999"), "999"),
        (Decimal("0"), "0"),
        (Decimal("-2500"), "-2 500"),
        (Decimal("-1234.56"), "-1 234.56"),
        (Decimal("0.006"), "0.01"),
        # Money rounds half up, not to even.
        (Decimal("0.005"), "0.01"),
        (Decimal("-0.001"), "0"),
        (Decimal("1000000000"), "1 000 000 000"),
        (None, "—"),
    ],
)
def test_format_amount(value, expected):
    assert format_amount(value) == expected


def test_chat_data_carries_every_figure():
    data = json.loads(summary_chat_data(_summary(), "Личное", NOW, "https://app.example.test"))

    assert data["m"] == "Ноябрь 2026"
    assert data["c"] == "KZT"
    assert data["w"] == "Личное"
    assert data["b"] == "1 234 567.50"
    assert data["i"] == "500 000"
    assert data["s"] == "123 456.78"
    assert data["n"] == "376 543.22"
    assert data["x"] is False and data["bi"] is False
    assert data["t"] == int(NOW.timestamp())
    assert data["k"] == [["Продукты", "12 500", 42, "#ff8800"]]
    assert data["u"] == "https://app.example.test"


def test_chat_data_fits_limit_with_long_cyrillic_names_and_drops_categories():
    long_name = "Очень длинная категория расходов на всё подряд" * 3
    categories = [
        _category(name=f"{index} {long_name}", amount=Decimal("-123456789012.34"), percent=12.5, color="#abcdef12")
        for index in range(20)
    ]
    summary = _summary(categories=categories)
    workspace = "Семейное пространство с очень длинным названием " * 5
    url = "https://aurum.example.test/" + "п" * 150

    encoded = summary_chat_data(summary, workspace, NOW, url)

    assert len(encoded.encode("utf-8")) <= CHAT_DATA_LIMIT
    data = json.loads(encoded)
    assert data["m"] == "Ноябрь 2026" and data["c"] == "KZT"
    assert len(data["w"]) <= 40
    assert all(len(item[0]) <= 24 for item in data["k"])
    # Categories are capped first, then trimmed from the end; never more than 5.
    assert len(data["k"]) <= 5


def test_chat_data_drops_categories_instead_of_failing_with_four_byte_characters():
    # Emoji are 4 bytes in UTF-8 and quotes/backslashes double when escaped.
    name = "\U0001f4b8" * 30
    tricky = '"\\' * 20
    categories = [_category(name=name if i % 2 else tricky, color="#123") for i in range(5)]
    url = "https://aurum.example.test/" + "x" * 170

    encoded = summary_chat_data(_summary(categories=categories), "\U0001f3e0" * 60, NOW, url)

    assert len(encoded.encode("utf-8")) <= CHAT_DATA_LIMIT
    data = json.loads(encoded)
    assert data["m"] == "Ноябрь 2026"
    assert len(data["k"]) <= 5


def test_chat_data_with_missing_amounts_and_incomplete_flags():
    summary = _summary(
        categories=[_category(amount=None)],
        income=None,
        spent=None,
        net=None,
        incomplete=True,
        balance_incomplete=True,
    )

    data = json.loads(summary_chat_data(summary, "Личное", NOW))

    assert data["i"] == data["s"] == data["n"] == "—"
    assert data["k"][0][1] == "—"
    assert data["x"] is True and data["bi"] is True
    assert "u" not in data


@pytest.mark.parametrize("color", ["red", "#12", "#GGGGGG", "url(javascript:1)", "#fff;background:url(x)", ""])
def test_invalid_category_color_is_blanked(color):
    data = json.loads(summary_chat_data(_summary(categories=[_category(color=color)]), "Личное", NOW))

    assert data["k"][0][3] == ""


def test_overlong_webapp_url_is_left_out():
    data = json.loads(summary_chat_data(_summary(), "Личное", NOW, "https://a.test/" + "x" * 300))

    assert "u" not in data


def test_widget_html_fits_bot_api_limits():
    html_bytes = SUMMARY_WIDGET_HTML.encode("utf-8")

    assert len(html_bytes) <= 32768
    assert len(zlib.compress(html_bytes, 9)) <= 4096
    assert "\x00" not in SUMMARY_WIDGET_HTML
    assert "chatData" in SUMMARY_WIDGET_HTML


def test_caption_and_text_fallback_contain_the_figures():
    summary = _summary(categories=[_category(), _category(name="Транспорт", amount=Decimal("3000"), percent=10.2)])

    caption = summary_caption(summary, "Личное")
    text = summary_text(summary, "Личное")

    assert caption == "Сводка: Ноябрь 2026 · Личное"
    assert text.startswith(caption)
    for line in (
        "Баланс: 1 234 567.50 KZT",
        "Доход: 500 000 KZT",
        "Расход: 123 456.78 KZT",
        "Итог: 376 543.22 KZT",
        "• Продукты: 12 500 KZT (42%)",
        "• Транспорт: 3 000 KZT (10%)",
    ):
        assert line in text
    assert "без курса" not in text


def test_text_fallback_warns_about_missing_rates_and_shows_dashes():
    text = summary_text(_summary(categories=[], income=None, incomplete=True), "Личное")

    assert "Доход: — KZT" in text
    assert "без курса валют" in text
    assert "•" not in text


def test_caption_is_capped_at_telegram_limit():
    assert len(summary_caption(_summary(), "я" * 5000)) == 1024
