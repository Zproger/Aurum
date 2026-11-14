"""Long-range spending reports — the analysis the month-scoped Dashboard
breakdown can't answer on its own: "how much did I spend on X this month,
and how much in total over N years" (single-category detail), and "which
categories cost the most over this whole period" (ranking, across all
categories of one kind at once, not just the current month).
"""
from collections import defaultdict
from datetime import date as date_
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, filter_accounts, scope_to_workspace
from app.models.category import Category
from app.models.account import Account
from app.models.enums import CategoryKind, TransactionType
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.reports import (
    CategoryRankingChildItem,
    CategoryRankingItem,
    CategoryRankingReport,
    CategorySpendingPoint,
    CategorySpendingReport,
)
from app.services.category_rollup import rollup_spending_by_top_level_category
from app.services.currency import split_amount_kzt, transaction_amount_kzt
from app.services.reporting_currency import reporting_converter


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def get_category_spending_report(
    session: AsyncSession,
    category_id: int,
    start_date: date_ | None,
    end_date: date_ | None,
    context: RequestWorkspace,
    account_ids: AccountIds = None,
) -> CategorySpendingReport:
    category = (
        await session.execute(
            scope_to_workspace(select(Category).where(Category.id == category_id), Category, context)
        )
    ).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # A top-level category's own report folds in its subcategories' spending
    # too (same rollup as the Dashboard breakdown); a subcategory picked
    # directly shows just its own transactions — there's nothing beneath it.
    category_ids: list[int] = [category_id]
    if category.parent_id is None:
        child_ids = (
            await session.execute(
                scope_to_workspace(
                    select(Category.id).where(Category.parent_id == category_id), Category, context
                )
            )
        ).scalars().all()
        category_ids.extend(child_ids)

    # Plain transactions filed directly under one of these categories, plus
    # split lines that assign part of a transaction to one of them — same
    # two sources category_rollup.py unions for the Dashboard/ranking report.
    plain_stmt = (
        select(Transaction.id, Transaction.date, transaction_amount_kzt())
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.category_id.in_(category_ids))
    )
    plain_stmt = scope_to_workspace(plain_stmt, Transaction, context)
    plain_stmt = scope_to_workspace(plain_stmt, Account, context)
    split_stmt = (
        select(TransactionSplit.transaction_id, Transaction.date, split_amount_kzt())
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(TransactionSplit.category_id.in_(category_ids))
    )
    split_stmt = scope_to_workspace(split_stmt, Transaction, context)
    split_stmt = scope_to_workspace(split_stmt, Account, context)
    plain_stmt = filter_accounts(plain_stmt, Transaction.account_id, account_ids)
    split_stmt = filter_accounts(split_stmt, Transaction.account_id, account_ids)
    if start_date:
        plain_stmt = plain_stmt.where(Transaction.date >= start_date)
        split_stmt = split_stmt.where(Transaction.date >= start_date)
    if end_date:
        plain_stmt = plain_stmt.where(Transaction.date <= end_date)
        split_stmt = split_stmt.where(Transaction.date <= end_date)

    plain_rows = (await session.execute(plain_stmt)).all()
    split_rows = (await session.execute(split_stmt)).all()
    contributions = [(r[0], r[1], r[2]) for r in plain_rows if r[2] is not None] + [
        (r[0], r[1], r[2]) for r in split_rows if r[2] is not None
    ]

    converter = await reporting_converter(session, context.workspace_id)
    empty = CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=start_date,
        end_date=end_date,
        reporting_currency=converter.currency,
        total_amount=Decimal("0"),
        transaction_count=0,
        average_per_month=Decimal("0"),
        series=[],
    )
    if not contributions:
        return empty

    dates = [txn_date for _, txn_date, _ in contributions]
    effective_start = start_date or min(dates)
    effective_end = end_date or max(dates)

    by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for _, txn_date, amount in contributions:
        by_month[(txn_date.year, txn_date.month)] += amount

    # Distinct transactions, not rows — a transaction split across two of
    # these categories (e.g. parent + one of its children) must count once,
    # the same as a plain transaction filed under just one of them.
    total_count = len({transaction_id for transaction_id, _, _ in contributions})

    series: list[CategorySpendingPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        # Summed in KZT, converted once per month at that month's end rate.
        amount = await converter.convert_month(by_month.get((year, month), Decimal("0")), year, month)
        series.append(CategorySpendingPoint(year=year, month=month, amount=amount))
        year, month = _next_month(year, month)

    # The total is the sum of the bars the chart draws, so the two always
    # agree; a month without a rate is left out and flagged as incomplete.
    total_amount = sum((point.amount for point in series if point.amount is not None), Decimal("0"))
    await converter.commit_fetched()

    months_count = len(series)
    average_per_month = (total_amount / months_count).quantize(Decimal("0.01")) if months_count else Decimal("0")

    return CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=effective_start,
        end_date=effective_end,
        reporting_currency=converter.currency,
        incomplete=converter.incomplete,
        total_amount=total_amount,
        transaction_count=total_count,
        average_per_month=average_per_month,
        series=series,
    )


_KIND_TO_TRANSACTION_TYPE = {
    CategoryKind.EXPENSE: TransactionType.EXPENSE,
    CategoryKind.INCOME: TransactionType.INCOME,
}


async def get_category_ranking_report(
    session: AsyncSession,
    kind: CategoryKind,
    start_date: date_ | None,
    end_date: date_ | None,
    context: RequestWorkspace,
    account_ids: AccountIds = None,
) -> CategoryRankingReport:
    """All categories of one kind, ranked by total spent/earned over an
    arbitrary period — "which category costs the most" across the whole
    range, unlike the month-scoped Dashboard breakdown or the
    single-category detail above."""
    # A transaction's type already restricts it to categories of the
    # matching kind (enforced at write time by _ensure_category_matches_type
    # in routes/transactions.py), so filtering by transaction_type below is
    # enough — no separate kind filter needed, and the shared rollup already
    # unions plain transactions with split lines the same way the Dashboard
    # breakdown does.
    rows = await rollup_spending_by_top_level_category(
        session,
        transaction_type=_KIND_TO_TRANSACTION_TYPE[kind],
        start_date=start_date,
        end_date=end_date,
        context=context,
        account_ids=account_ids,
    )
    total_amount = sum((row.amount for row in rows), Decimal("0"))

    def _percent(amount: Decimal) -> float:
        # A ratio of two KZT sums — exact in any reporting currency.
        return float(amount / total_amount * 100) if total_amount else 0.0

    # One rate for the whole period: its end (today when open-ended or still
    # running).
    converter = await reporting_converter(session, context.workspace_id)
    period_end = end_date or converter.today

    items = [
        CategoryRankingItem(
            category_id=row.category_id,
            name=row.name,
            color=row.color,
            icon=row.icon,
            amount=await converter.convert(row.amount, period_end),
            percent=_percent(row.amount),
            transaction_count=row.transaction_count,
            children=[
                CategoryRankingChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=await converter.convert(child.amount, period_end),
                )
                for child in row.children
            ],
        )
        for row in rows
    ]
    total_reporting = await converter.convert(total_amount, period_end)
    await converter.commit_fetched()

    return CategoryRankingReport(
        start_date=start_date,
        end_date=end_date,
        reporting_currency=converter.currency,
        incomplete=converter.incomplete,
        total_amount=total_reporting,
        items=items,
    )
