"""Long-range spending reports — the analysis the month-scoped Dashboard
breakdown can't answer on its own: "how much did I spend on X this month,
and how much in total over N years" (single-category detail), and "which
categories cost the most over this whole period" (ranking, across all
categories of one kind at once, not just the current month).

The same two shapes exist tag-side (get_tag_ranking_report /
get_tag_spending_report): a category answers "what kind of spend was this",
a tag answers "which event/project did it belong to" (models/tag.py), so
the tag reports are what answer "how much did this trip / these gifts cost
me", cutting across categories instead of along them.
"""
from collections import defaultdict
from datetime import date as date_
from decimal import Decimal
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.tag import Tag, transaction_tags
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.reports import (
    CategoryRankingChildItem,
    CategoryRankingItem,
    CategoryRankingReport,
    CategorySpendingPoint,
    CategorySpendingReport,
    TagRankingCategoryItem,
    TagRankingItem,
    TagRankingReport,
    TagSpendingReport,
)
from app.services.category_rollup import rollup_spending_by_top_level_category
from app.services.tag_rollup import rollup_spending_by_tag


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


class _MonthlySummary(NamedTuple):
    start_date: date_
    end_date: date_
    total_amount: Decimal
    transaction_count: int
    average_per_month: Decimal
    series: list[CategorySpendingPoint]


def _summarize_by_month(
    contributions: list[tuple[int, date_, Decimal]], start_date: date_ | None, end_date: date_ | None
) -> _MonthlySummary:
    """Turns (transaction_id, date, amount) rows into the month-by-month
    shape both detail reports return — gap months included as zeroes so the
    chart's bars stay evenly spaced in time, and the period falling back to
    the data's own first/last month when the caller didn't bound it.

    Shared by the category and tag detail reports so the two can't drift on
    what "average per month" or "transaction count" mean. Callers must
    handle an empty `contributions` list themselves: with no rows there is
    no period to fall back to.
    """
    dates = [txn_date for _, txn_date, _ in contributions]
    effective_start = start_date or min(dates)
    effective_end = end_date or max(dates)

    by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for _, txn_date, amount in contributions:
        by_month[(txn_date.year, txn_date.month)] += amount

    total_amount = sum((amount for _, _, amount in contributions), Decimal("0"))
    # Distinct transactions, not rows — a transaction split across two
    # categories (e.g. parent + one of its children) must count once, the
    # same as a plain transaction filed under just one of them.
    total_count = len({transaction_id for transaction_id, _, _ in contributions})

    series: list[CategorySpendingPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        series.append(CategorySpendingPoint(year=year, month=month, amount=by_month.get((year, month), Decimal("0"))))
        year, month = _next_month(year, month)

    months_count = len(series)
    average_per_month = (total_amount / months_count).quantize(Decimal("0.01")) if months_count else Decimal("0")

    return _MonthlySummary(
        start_date=effective_start,
        end_date=effective_end,
        total_amount=total_amount,
        transaction_count=total_count,
        average_per_month=average_per_month,
        series=series,
    )


async def get_category_spending_report(
    session: AsyncSession, category_id: int, start_date: date_ | None, end_date: date_ | None
) -> CategorySpendingReport:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # A top-level category's own report folds in its subcategories' spending
    # too (same rollup as the Dashboard breakdown); a subcategory picked
    # directly shows just its own transactions — there's nothing beneath it.
    category_ids: list[int] = [category_id]
    if category.parent_id is None:
        child_ids = (
            await session.execute(select(Category.id).where(Category.parent_id == category_id))
        ).scalars().all()
        category_ids.extend(child_ids)

    # Plain transactions filed directly under one of these categories, plus
    # split lines that assign part of a transaction to one of them — same
    # two sources category_rollup.py unions for the Dashboard/ranking report.
    plain_stmt = select(Transaction.id, Transaction.date, Transaction.amount).where(
        Transaction.category_id.in_(category_ids)
    )
    split_stmt = (
        select(TransactionSplit.transaction_id, Transaction.date, TransactionSplit.amount)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(TransactionSplit.category_id.in_(category_ids))
    )
    if start_date:
        plain_stmt = plain_stmt.where(Transaction.date >= start_date)
        split_stmt = split_stmt.where(Transaction.date >= start_date)
    if end_date:
        plain_stmt = plain_stmt.where(Transaction.date <= end_date)
        split_stmt = split_stmt.where(Transaction.date <= end_date)

    plain_rows = (await session.execute(plain_stmt)).all()
    split_rows = (await session.execute(split_stmt)).all()
    contributions = [(r[0], r[1], r[2]) for r in plain_rows] + [(r[0], r[1], r[2]) for r in split_rows]

    empty = CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=start_date,
        end_date=end_date,
        total_amount=Decimal("0"),
        transaction_count=0,
        average_per_month=Decimal("0"),
        series=[],
    )
    if not contributions:
        return empty

    summary = _summarize_by_month(contributions, start_date, end_date)

    return CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=summary.start_date,
        end_date=summary.end_date,
        total_amount=summary.total_amount,
        transaction_count=summary.transaction_count,
        average_per_month=summary.average_per_month,
        series=summary.series,
    )


_KIND_TO_TRANSACTION_TYPE = {
    CategoryKind.EXPENSE: TransactionType.EXPENSE,
    CategoryKind.INCOME: TransactionType.INCOME,
}


async def get_category_ranking_report(
    session: AsyncSession, kind: CategoryKind, start_date: date_ | None, end_date: date_ | None
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
        session, transaction_type=_KIND_TO_TRANSACTION_TYPE[kind], start_date=start_date, end_date=end_date
    )
    total_amount = sum((row.amount for row in rows), Decimal("0"))

    def _percent(amount: Decimal) -> float:
        return float(amount / total_amount * 100) if total_amount else 0.0

    items = [
        CategoryRankingItem(
            category_id=row.category_id,
            name=row.name,
            color=row.color,
            icon=row.icon,
            amount=row.amount,
            percent=_percent(row.amount),
            transaction_count=row.transaction_count,
            children=[
                CategoryRankingChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=child.amount,
                )
                for child in row.children
            ],
        )
        for row in rows
    ]

    return CategoryRankingReport(start_date=start_date, end_date=end_date, total_amount=total_amount, items=items)


async def _period_total(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    start_date: date_ | None,
    end_date: date_ | None,
    tagged_only: bool = False,
) -> Decimal:
    """Everything spent/earned in the period — or only the part carrying at
    least one tag. `Transaction.tags.any()` is an EXISTS, so a transaction
    with three tags is still counted once; summing the ranking's items
    instead would count it three times."""
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == transaction_type)
    if tagged_only:
        stmt = stmt.where(Transaction.tags.any())
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    return Decimal(str((await session.execute(stmt)).scalar_one()))


async def get_tag_ranking_report(
    session: AsyncSession, kind: CategoryKind, start_date: date_ | None, end_date: date_ | None
) -> TagRankingReport:
    """Every tag ranked by total spent/earned over an arbitrary period —
    "which trip/project/person cost the most", the question the category
    ranking above can't answer because one such answer cuts across several
    categories at once.

    Each tag is measured against the period's *whole* spending rather than
    against the other tags: tags overlap, so a denominator built from the
    items themselves would double-count every multi-tagged transaction and
    quietly shrink each percentage.
    """
    transaction_type = _KIND_TO_TRANSACTION_TYPE[kind]
    rows = await rollup_spending_by_tag(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date
    )
    total_amount = await _period_total(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date
    )
    tagged_amount = await _period_total(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date, tagged_only=True
    )

    def _percent(amount: Decimal) -> float:
        return float(amount / total_amount * 100) if total_amount else 0.0

    items = [
        TagRankingItem(
            tag_id=row.tag_id,
            name=row.name,
            color=row.color,
            amount=row.amount,
            percent=_percent(row.amount),
            transaction_count=row.transaction_count,
            categories=[
                TagRankingCategoryItem(
                    category_id=category.category_id, name=category.name, color=category.color,
                    icon=category.icon, amount=category.amount,
                )
                for category in row.categories
            ],
        )
        for row in rows
    ]

    return TagRankingReport(
        start_date=start_date,
        end_date=end_date,
        total_amount=total_amount,
        tagged_amount=tagged_amount,
        items=items,
    )


async def get_tag_spending_report(
    session: AsyncSession, tag_id: int, kind: CategoryKind, start_date: date_ | None, end_date: date_ | None
) -> TagSpendingReport:
    """One tag's spend over time. Unlike its category twin this needs no
    split-line union: a tag sits on the transaction itself, so the
    transaction's own amount is the whole of its contribution however many
    categories it was split across.

    `kind` is a parameter here rather than a property of the subject — a
    category is either an expense or an income one, but a tag is neither and
    can legitimately sit on both sides ("trip:georgia" on the flights and on
    the refund), so the caller picks which side it's looking at.
    """
    tag = await session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    stmt = (
        select(Transaction.id, Transaction.date, Transaction.amount)
        .join(transaction_tags, transaction_tags.c.transaction_id == Transaction.id)
        .where(transaction_tags.c.tag_id == tag_id, Transaction.type == _KIND_TO_TRANSACTION_TYPE[kind])
    )
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)

    contributions = [(r[0], r[1], r[2]) for r in (await session.execute(stmt)).all()]
    if not contributions:
        return TagSpendingReport(
            tag_id=tag.id,
            tag_name=tag.name,
            start_date=start_date,
            end_date=end_date,
            total_amount=Decimal("0"),
            transaction_count=0,
            average_per_month=Decimal("0"),
            series=[],
        )

    summary = _summarize_by_month(contributions, start_date, end_date)
    return TagSpendingReport(
        tag_id=tag.id,
        tag_name=tag.name,
        start_date=summary.start_date,
        end_date=summary.end_date,
        total_amount=summary.total_amount,
        transaction_count=summary.transaction_count,
        average_per_month=summary.average_per_month,
        series=summary.series,
    )
