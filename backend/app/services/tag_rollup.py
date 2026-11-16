"""Spend/income per tag over a period, with each tag's total broken down by
top-level category — the tag-side mirror of category_rollup.py, and the data
behind the Reports page's tag ranking.

Two things follow from where a tag actually lives (models/tag.py: a label on
the *transaction*, not on a category or a split line) and make this rollup
behave differently from the category one:

* A tagged transaction contributes its **whole** amount to the tag, even when
  its categories are split several ways — the split only decides how that
  amount is attributed *inside* the tag's breakdown, never how much the tag
  itself is worth.
* Tags overlap freely: one transaction can carry any number of them, so tag
  totals can legitimately sum to more than the period actually saw. Callers
  must not treat the sum of these items as a period total — see
  reports_service.get_tag_ranking_report, which measures each tag against the
  period's real spending instead.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.tag import Tag, transaction_tags
from app.models.transaction import Transaction
from app.services.category_rollup import raw_category_contributions

# Same neutral the category rollup falls back to for a category that no
# longer exists — reused here for the "no category at all" bucket.
NEUTRAL_COLOR = "#898781"


@dataclass
class TagRollupCategoryItem:
    """One top-level category's share of a tag's total. category_id is None
    for the amount that had no category to attribute at all (a transaction
    saved without one) — kept as an explicit bucket so the breakdown still
    adds up to the tag's total instead of silently losing money."""

    category_id: int | None
    name: str
    color: str
    icon: str | None
    amount: Decimal


@dataclass
class TagRollupItem:
    tag_id: int
    name: str
    amount: Decimal
    # Distinct transactions carrying this tag — a transaction_tags row is
    # unique per (transaction, tag) pair, so every joined row is already one
    # distinct transaction and no de-duplication is needed here.
    transaction_count: int
    # A tag has no color of its own (models/tag.py) — it borrows the color of
    # the category it spent the most on, so the ranking bar still reads as
    # "this is mostly restaurants" at a glance. NEUTRAL_COLOR when there's
    # nothing to borrow from.
    color: str
    categories: list[TagRollupCategoryItem] = field(default_factory=list)


async def rollup_spending_by_tag(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    start_date: date_ | None = None,
    end_date: date_ | None = None,
) -> list[TagRollupItem]:
    """Every tag's total for the period, sorted by amount desc (tag name as
    tiebreak so equal-amount tags keep a stable, readable order)."""
    tag_stmt = (
        select(Tag.id, Tag.name, Transaction.id, Transaction.amount)
        .join(transaction_tags, transaction_tags.c.tag_id == Tag.id)
        .join(Transaction, Transaction.id == transaction_tags.c.transaction_id)
        .where(Transaction.type == transaction_type)
    )
    if start_date is not None:
        tag_stmt = tag_stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        tag_stmt = tag_stmt.where(Transaction.date <= end_date)

    tagged_rows = (await session.execute(tag_stmt)).all()
    if not tagged_rows:
        return []

    # The same (transaction_id, category_id, amount) contributions the
    # category ranking rolls up — reused here to answer "what was this tag
    # spent on", so a split transaction's share lands under each category it
    # genuinely touched rather than all under one.
    contributions = await raw_category_contributions(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date
    )
    categories_by_id = {c.id: c for c in (await session.execute(select(Category))).scalars().all()}

    # transaction_id -> {top-level category id: that category's share of it}
    shares_by_transaction: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for transaction_id, category_id, amount in contributions:
        category = categories_by_id.get(category_id)
        effective_id = category.parent_id if category and category.parent_id is not None else category_id
        shares_by_transaction[transaction_id][effective_id] += amount

    names: dict[int, str] = {}
    amount_by_tag: dict[int, Decimal] = defaultdict(Decimal)
    count_by_tag: dict[int, int] = defaultdict(int)
    category_amounts: dict[int, dict[int | None, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

    for tag_id, tag_name, transaction_id, amount in tagged_rows:
        names[tag_id] = tag_name
        amount_by_tag[tag_id] += amount
        count_by_tag[tag_id] += 1
        shares = shares_by_transaction.get(transaction_id)
        if shares:
            for effective_id, share in shares.items():
                category_amounts[tag_id][effective_id] += share
        else:
            # Neither a category of its own nor split lines — still real
            # money the tag is responsible for, so it gets its own bucket.
            category_amounts[tag_id][None] += amount

    items: list[TagRollupItem] = []
    for tag_id, amount in amount_by_tag.items():
        breakdown = [
            TagRollupCategoryItem(
                category_id=category_id,
                name=_category_name(categories_by_id.get(category_id) if category_id is not None else None),
                color=_category_color(categories_by_id.get(category_id) if category_id is not None else None),
                icon=categories_by_id[category_id].icon if category_id in categories_by_id else None,
                amount=category_amount,
            )
            for category_id, category_amount in sorted(
                category_amounts[tag_id].items(), key=lambda pair: -pair[1]
            )
        ]
        items.append(
            TagRollupItem(
                tag_id=tag_id,
                name=names[tag_id],
                amount=amount,
                transaction_count=count_by_tag[tag_id],
                color=breakdown[0].color if breakdown else NEUTRAL_COLOR,
                categories=breakdown,
            )
        )
    items.sort(key=lambda item: (-item.amount, item.name))
    return items


def _category_name(category: Category | None) -> str:
    """An empty name marks the no-category bucket, which the frontend labels
    from its own translations rather than from a raw backend string (the
    breakdown is bilingual like every other category label)."""
    return category.name if category is not None else ""


def _category_color(category: Category | None) -> str:
    return category.color if category is not None else NEUTRAL_COLOR
