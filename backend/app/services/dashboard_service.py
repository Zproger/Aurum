"""Aggregation logic behind the Overview dashboard."""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, filter_accounts, scope_to_workspace
from app.models.enums import TransactionPurpose, TransactionType
from app.models.account import Account
from app.models.exchange_rate import ExchangeRate
from app.models.transaction import Transaction
from app.schemas.dashboard import (
    BalanceSummary,
    CategoryBreakdownChildItem,
    CategoryBreakdownItem,
    CurrencyBalance,
    DashboardSummary,
)
from app.services.account_service import account_balances
from app.services.category_rollup import rollup_spending_by_top_level_category
from app.services.currency import transaction_amount_kzt
from app.services.exchange_rate_service import get_exchange_rate
from app.services.reporting_currency import reporting_converter
from app.services.settings_service import get_or_create_app_settings

# Categorical slots are capped at 8 (dataviz skill: a 9th series folds into "Other",
# never a generated hue) — this is also the exact size of the default category set.
MAX_CHART_SLICES = 8
OTHER_SLICE_COLOR = "#898781"  # muted ink, reserved for the non-categorical rollup

# A currency with nothing cached at all gets one short, bounded attempt at an
# official rate, so a fresh install with a foreign account shows a real number
# instead of a permanent "no rate". A currency that already has a cached rate
# never triggers a network call here — a dashboard load must not wait on NBK.
COLD_RATE_TIMEOUT_SECONDS = 3.0


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


async def _rate_to_kzt(session: AsyncSession, as_of: date, currency: str) -> tuple[Decimal | None, date | None]:
    """The official rate for one currency, or (None, None) when none could be
    established. KZT is its own identity, so it never needs a lookup."""
    currency = currency.upper()
    if currency == "KZT":
        return Decimal("1"), as_of

    cached = (
        await session.execute(
            select(ExchangeRate)
            .where(ExchangeRate.currency == currency, ExchangeRate.requested_date <= as_of)
            .order_by(ExchangeRate.requested_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if cached is None:
        # Nothing cached on or before this date. A later official rate is still
        # a real rate, and `rate_date` travels with it so the UI can say which
        # day it belongs to.
        cached = (
            await session.execute(
                select(ExchangeRate)
                .where(ExchangeRate.currency == currency)
                .order_by(ExchangeRate.requested_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if cached is None:
        try:
            cached = await get_exchange_rate(session, as_of, currency, timeout=COLD_RATE_TIMEOUT_SECONDS)
        except HTTPException:
            return None, None
    return cached.rate_to_kzt, cached.effective_date


async def get_balance_summary(
    session: AsyncSession, as_of: date, context: RequestWorkspace, account_ids: AccountIds = None
) -> BalanceSummary:
    """Total money across every account, expressed in the app's reporting
    currency.

    Each account holds its balance in its own currency; this is the one place
    they're added up. Everything converts through KZT — that's the currency the
    official rates are quoted in — and then into the reporting currency, so a
    future non-KZT reporting currency needs no new rate plumbing.

    A currency with no usable rate is reported as such rather than dropped: its
    balance stays visible, it just doesn't contribute to the total, and
    `incomplete` says so.
    """
    reporting_currency = (await get_or_create_app_settings(session, context)).currency.upper()
    balances, _ = await account_balances(session, context)
    accounts = (
        await session.execute(
            filter_accounts(scope_to_workspace(select(Account), Account, context), Account.id, account_ids)
        )
    ).scalars().all()

    by_currency: dict[str, Decimal] = defaultdict(Decimal)
    for account in accounts:
        by_currency[account.currency.upper()] += balances.get(account.id, Decimal("0"))

    reporting_rate, _ = await _rate_to_kzt(session, as_of, reporting_currency)

    items: list[CurrencyBalance] = []
    total = Decimal("0")
    incomplete = False
    for currency in sorted(by_currency):
        amount = by_currency[currency]
        if amount == 0:
            # Zero is zero in every currency — no rate needed, and no reason to
            # reach for one (or to call the currency unconvertible).
            items.append(CurrencyBalance(currency=currency, amount=amount, amount_reporting=Decimal("0")))
            continue
        rate, rate_date = await _rate_to_kzt(session, as_of, currency)
        if rate is None or reporting_rate is None:
            incomplete = True
            items.append(CurrencyBalance(currency=currency, amount=amount))
            continue
        converted = (amount * rate / reporting_rate).quantize(Decimal("0.01"))
        total += converted
        items.append(
            CurrencyBalance(
                currency=currency,
                amount=amount,
                amount_reporting=converted,
                rate_to_kzt=rate,
                rate_date=rate_date,
            )
        )
    return BalanceSummary(
        reporting_currency=reporting_currency, total=total, incomplete=incomplete, items=items
    )


async def get_dashboard_summary(
    session: AsyncSession, year: int, month: int, context: RequestWorkspace, account_ids: AccountIds = None
) -> DashboardSummary:
    start, end = _month_bounds(year, month)

    totals_stmt = (
        select(Transaction.type, func.coalesce(func.sum(transaction_amount_kzt()), 0))
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.purpose != TransactionPurpose.INVESTMENT_TRADE,
        )
        .group_by(Transaction.type)
    )
    totals_stmt = scope_to_workspace(totals_stmt, Transaction, context)
    totals_stmt = scope_to_workspace(totals_stmt, Account, context)
    totals_stmt = filter_accounts(totals_stmt, Transaction.account_id, account_ids)
    totals_result = await session.execute(totals_stmt)
    totals: dict[TransactionType, Decimal] = {row[0]: row[1] for row in totals_result.all()}

    real_income = totals.get(TransactionType.INCOME, Decimal("0"))
    spent = totals.get(TransactionType.EXPENSE, Decimal("0"))
    transferred_out = totals.get(TransactionType.TRANSFER, Decimal("0"))

    # A subcategory's spending rolls up into its parent's slice, and a split
    # transaction's category_id=NULL means its category lives on its split
    # lines instead — rollup_spending_by_top_level_category handles both
    # the same way a plain transaction's category already was.
    rows = await rollup_spending_by_top_level_category(
        session,
        transaction_type=TransactionType.EXPENSE,
        start_date=start,
        end_date=end,
        context=context,
        account_ids=account_ids,
    )

    top_rows, rest_rows = rows[:MAX_CHART_SLICES], rows[MAX_CHART_SLICES:]

    # Every sum above is in KZT; the page reports in the workspace currency.
    # Each total converts once, at the official rate for the month's last day
    # (today while the month is still running) — KZT reporting passes through.
    converter = await reporting_converter(session, context.workspace_id)

    async def _reporting(amount: Decimal) -> Decimal | None:
        return await converter.convert_month(amount, year, month)

    def _percent(amount: Decimal) -> float:
        # A ratio of two KZT sums — exact in any reporting currency.
        return float(amount / spent * 100) if spent else 0.0

    spending_by_category = [
        CategoryBreakdownItem(
            category_id=row.category_id, name=row.name, color=row.color, icon=row.icon,
            amount=await _reporting(row.amount), percent=_percent(row.amount),
            children=[
                CategoryBreakdownChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=await _reporting(child.amount),
                )
                for child in row.children
            ],
        )
        for row in top_rows
    ]

    if rest_rows:
        other_amount = sum((row.amount for row in rest_rows), Decimal("0"))
        spending_by_category.append(
            CategoryBreakdownItem(
                category_id=None, name="Other", color=OTHER_SLICE_COLOR, icon="more-horizontal",
                amount=await _reporting(other_amount), percent=_percent(other_amount),
            )
        )

    real_income_reporting = await _reporting(real_income)
    spent_reporting = await _reporting(spent)
    # Net is the difference of the two figures the page shows, so the three
    # cards always add up to the cent.
    net_reporting = (
        real_income_reporting - spent_reporting
        if real_income_reporting is not None and spent_reporting is not None
        else None
    )
    transferred_out_reporting = await _reporting(transferred_out)

    # All-time, not month-scoped — the money actually sitting in the accounts.
    balance = await get_balance_summary(session, date.today(), context, account_ids)
    # get_balance_summary (or the converter) may have cached a freshly fetched
    # official rate; this is a GET, but that write is the same one the
    # /exchange-rates route makes.
    await session.commit()

    return DashboardSummary(
        year=year,
        month=month,
        reporting_currency=converter.currency,
        incomplete=converter.incomplete,
        real_income=real_income_reporting,
        spent=spent_reporting,
        net=net_reporting,
        transferred_out=transferred_out_reporting,
        spending_by_category=spending_by_category,
        balance=balance,
    )
