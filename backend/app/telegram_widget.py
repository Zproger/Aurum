"""Monthly summary rendered as a Bot API 10.4 HTML widget.

The widget HTML is static and can never be replaced after sending, so every
figure travels in the message's chat_data (max 1024 bytes) and the template
draws itself from it. Amounts are formatted here so the widget stays tiny.
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import re

from app.schemas.dashboard import DashboardSummary
from app.telegram_labels import category_label

SUMMARY_WIDGET_HTML = (Path(__file__).parent / "telegram_widgets" / "summary.html").read_text(encoding="utf-8")
# Fits the header, three totals, five categories, the note and the buttons.
SUMMARY_WIDGET_HEIGHT = 400
CHAT_DATA_LIMIT = 1024
MAX_CATEGORIES = 5
CATEGORY_NAME_LIMIT = 24
WORKSPACE_NAME_LIMIT = 40
WEBAPP_URL_LIMIT = 200
MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
MISSING = "—"


def format_amount(value: Decimal | None) -> str:
    """1234567.5 → «1 234 567.50»; whole numbers lose the «.00»; None → «—»."""
    if value is None:
        return MISSING
    quantized = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    whole, fraction = f"{abs(quantized):.2f}".split(".")
    grouped = f"{int(whole):,}".replace(",", " ")
    return f"{sign}{grouped}" if fraction == "00" else f"{sign}{grouped}.{fraction}"


def month_label(summary: DashboardSummary) -> str:
    return f"{MONTHS[summary.month - 1]} {summary.year}"


def summary_chat_data(
    summary: DashboardSummary,
    workspace_name: str,
    now: datetime,
    webapp_url: str = "",
) -> str:
    """Compact JSON for chat_data; categories are dropped from the end until it fits."""
    data: dict = {
        "v": 1,
        "m": month_label(summary),
        "w": workspace_name[:WORKSPACE_NAME_LIMIT],
        "c": summary.reporting_currency,
        "b": format_amount(summary.balance.total),
        "bi": summary.balance.incomplete,
        "i": format_amount(summary.real_income),
        "s": format_amount(summary.spent),
        "n": format_amount(summary.net),
        "x": summary.incomplete,
        "t": int(now.timestamp()),
        "k": [
            [
                category_label(item.name)[:CATEGORY_NAME_LIMIT],
                format_amount(item.amount),
                round(item.percent),
                item.color if HEX_COLOR_RE.fullmatch(item.color or "") else "",
            ]
            for item in summary.spending_by_category[:MAX_CATEGORIES]
        ],
    }
    if webapp_url and len(webapp_url) <= WEBAPP_URL_LIMIT:
        data["u"] = webapp_url
    while True:
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= CHAT_DATA_LIMIT:
            return encoded
        if data["k"]:
            data["k"].pop()
        elif "u" in data:
            del data["u"]
        else:
            # Cannot happen with the limits above; keep the essentials only.
            data["w"] = data["w"][:10]
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def summary_caption(summary: DashboardSummary, workspace_name: str) -> str:
    return f"Сводка: {month_label(summary)} · {workspace_name}"[:1024]


def summary_text(summary: DashboardSummary, workspace_name: str) -> str:
    """Plain-text fallback when the client or API cannot show the widget."""
    currency = summary.reporting_currency
    lines = [
        summary_caption(summary, workspace_name),
        f"Баланс: {format_amount(summary.balance.total)} {currency}",
        f"Доход: {format_amount(summary.real_income)} {currency}",
        f"Расход: {format_amount(summary.spent)} {currency}",
        f"Итог: {format_amount(summary.net)} {currency}",
    ]
    categories = summary.spending_by_category[:MAX_CATEGORIES]
    if categories:
        lines.append("")
        lines.extend(
            f"• {category_label(item.name)}: {format_amount(item.amount)} {currency} ({round(item.percent)}%)"
            for item in categories
        )
    if summary.incomplete or summary.balance.incomplete:
        lines.append("\nЧасть сумм без курса валют — проверьте в Aurum.")
    return "\n".join(lines)
