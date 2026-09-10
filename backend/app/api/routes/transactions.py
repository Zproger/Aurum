from datetime import date as date_
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.core.audit import log_destructive
from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.transaction import (
    TransactionBulkCreate,
    TransactionBulkCreateResult,
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionSplitInput,
    TransactionUpdate,
    split_rule_violation,
    transfer_rule_violation,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

_EAGER = (
    selectinload(Transaction.account),
    selectinload(Transaction.category),
    selectinload(Transaction.tags),
    selectinload(Transaction.splits).selectinload(TransactionSplit.category),
)


async def _resolve_tags(session: AsyncSession, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    result = await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
    tags = list(result.scalars().all())
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown tag id(s): {sorted(missing)}")
    return tags

_TYPE_TO_CATEGORY_KIND = {
    TransactionType.INCOME: CategoryKind.INCOME,
    TransactionType.EXPENSE: CategoryKind.EXPENSE,
}


async def _ensure_category_matches_type(
    session: AsyncSession, category_id: int | None, transaction_type: TransactionType
) -> Category | None:
    """A category picked for an income transaction must itself be an income
    category (and likewise for expense) — otherwise the dashboard's spending
    breakdown, which only joins EXPENSE-typed rows, would silently misclassify
    the entry. Returns the fetched category (or None for category_id=None) so
    callers that also need the row itself — _build_splits, below — don't have
    to fetch it a second time."""
    if category_id is None:
        return None
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} transaction",
        )
    return category


async def _build_splits(
    session: AsyncSession, splits: list[TransactionSplitInput], transaction_type: TransactionType
) -> list[TransactionSplit]:
    """A split's whole point is dividing one purchase's total across the
    *subcategories of one parent* (a hypermarket receipt: part groceries ->
    Sweets, part -> Alcohol) — not across unrelated top-level categories, or
    the numbers would roll up into two different parents and the "spent X on
    Groceries, split between Sweets/Alcohol" picture the feature exists for
    falls apart. Each split may point at that parent category itself (an
    unspecified-subcategory line) or at any one of its direct children —
    enforced by requiring every split's own top-level ancestor
    (parent_id, or its own id if it has none) to agree.
    """
    top_level_ids: set[int] = set()
    for split in splits:
        category = await _ensure_category_matches_type(session, split.category_id, transaction_type)
        assert category is not None  # split.category_id is required (not Optional) on the schema
        top_level_ids.add(category.parent_id if category.parent_id is not None else category.id)
    if len(top_level_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="All split categories must be the same parent category or its direct subcategories",
        )
    return [TransactionSplit(category_id=s.category_id, amount=s.amount, note=s.note) for s in splits]


@router.get("", response_model=TransactionPage)
async def list_transactions(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    account_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
    type: TransactionType | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=255),
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = Query(default="date_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TransactionPage:
    stmt = select(Transaction).options(*_EAGER)
    count_stmt = select(func.count()).select_from(Transaction)

    if year is not None:
        stmt = stmt.where(func.extract("year", Transaction.date) == year)
        count_stmt = count_stmt.where(func.extract("year", Transaction.date) == year)
    if month is not None:
        stmt = stmt.where(func.extract("month", Transaction.date) == month)
        count_stmt = count_stmt.where(func.extract("month", Transaction.date) == month)
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
        count_stmt = count_stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
        count_stmt = count_stmt.where(Transaction.date <= end_date)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
        count_stmt = count_stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        # A split transaction has category_id=NULL on the row itself — the
        # category lives on its split lines instead, so filtering by exact
        # column match alone would silently drop it from a category filter
        # it genuinely belongs to.
        category_filter = or_(
            Transaction.category_id == category_id, Transaction.splits.any(TransactionSplit.category_id == category_id)
        )
        stmt = stmt.where(category_filter)
        count_stmt = count_stmt.where(category_filter)
    if tag_id is not None:
        stmt = stmt.where(Transaction.tags.any(Tag.id == tag_id))
        count_stmt = count_stmt.where(Transaction.tags.any(Tag.id == tag_id))
    if type is not None:
        stmt = stmt.where(Transaction.type == type)
        count_stmt = count_stmt.where(Transaction.type == type)
    if search is not None:
        # Lets the user find a transaction from any period by keyword (e.g. an
        # item bought months ago) without knowing which month to look in first —
        # matches description, merchant, and notes so any of those fields can surface it.
        pattern = f"%{search.strip()}%"
        search_clause = or_(
            Transaction.description.ilike(pattern),
            Transaction.merchant.ilike(pattern),
            Transaction.notes.ilike(pattern),
        )
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    total = (await session.execute(count_stmt)).scalar_one()

    # id as a tiebreaker keeps pagination stable when many rows share a date/amount.
    if sort == "amount_desc":
        stmt = stmt.order_by(Transaction.amount.desc(), Transaction.id.desc())
    elif sort == "amount_asc":
        stmt = stmt.order_by(Transaction.amount.asc(), Transaction.id.desc())
    else:
        stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return TransactionPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/years", response_model=list[int])
async def list_transaction_years(session: AsyncSession = Depends(get_session)) -> list[int]:
    """Full range of years to offer in the year picker — from the earliest
    transaction through the current year, so a gap year with no activity
    still shows up (as zero) instead of silently disappearing from the UI."""
    bounds = await session.execute(select(func.min(Transaction.date), func.max(Transaction.date)))
    min_date, max_date = bounds.one()
    current_year = date_.today().year
    if min_date is None:
        return [current_year]
    return list(range(min_date.year, max(max_date.year, current_year) + 1))


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(payload: TransactionCreate, session: AsyncSession = Depends(get_session)) -> Transaction:
    await _ensure_category_matches_type(session, payload.category_id, payload.type)
    fields = payload.model_dump(exclude={"tag_ids", "splits"})
    transaction = Transaction(**fields)
    transaction.tags = await _resolve_tags(session, payload.tag_ids)
    if payload.splits:
        transaction.splits = await _build_splits(session, payload.splits, payload.type)
    session.add(transaction)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction.id)
    )
    return refreshed.scalar_one()


@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate, session: AsyncSession = Depends(get_session)
) -> TransactionBulkCreateResult:
    """CSV import lands here — see schemas.TransactionBulkCreate. All rows
    are validated before any is added, so a bad row 400s the whole request
    instead of leaving a half-imported statement behind."""
    for item in payload.items:
        await _ensure_category_matches_type(session, item.category_id, item.type)

    transactions = []
    for item in payload.items:
        transaction = Transaction(**item.model_dump(exclude={"tag_ids", "splits"}))
        transaction.tags = await _resolve_tags(session, item.tag_ids)
        if item.splits:
            transaction.splits = await _build_splits(session, item.splits, item.type)
        transactions.append(transaction)

    session.add_all(transactions)
    await session.commit()
    # One request can add thousands of rows (CSV import) — worth a line so an
    # unexpected pile of transactions can be dated later.
    log_destructive("transactions.bulk_created", count=len(transactions))
    return TransactionBulkCreateResult(created=len(transactions))


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int, payload: TransactionUpdate, session: AsyncSession = Depends(get_session)
) -> Transaction:
    # Eager-loads tags and splits — assigning transaction.tags/splits below
    # would otherwise lazy-load the current collection first to diff
    # against, which async SQLAlchemy can't do outside an explicit await
    # (MissingGreenlet).
    transaction = await session.get(
        Transaction, transaction_id, options=[selectinload(Transaction.tags), selectinload(Transaction.splits)]
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    updates = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "splits"})
    # Checks run against the row as it would look after the patch, not just
    # the fields sent: switching type alone can invalidate fields left
    # untouched.
    effective_type = updates.get("type", transaction.type)
    effective_category_id = updates.get("category_id", transaction.category_id)
    effective_account_id = updates.get("account_id", transaction.account_id)
    effective_transfer_account_id = updates.get("transfer_account_id", transaction.transfer_account_id)
    effective_amount = updates.get("amount", transaction.amount)
    await _ensure_category_matches_type(session, effective_category_id, effective_type)
    violation = transfer_rule_violation(
        type=effective_type,
        account_id=effective_account_id,
        transfer_account_id=effective_transfer_account_id,
        category_id=effective_category_id,
    )
    if violation:
        raise HTTPException(status_code=400, detail=violation)

    if payload.splits is not None:
        split_count = len(payload.splits)
        split_total = sum((s.amount for s in payload.splits), Decimal("0")) if payload.splits else None
    else:
        # Splits weren't touched by this patch — check the existing rows as
        # they stand. Reading straight off the ORM objects here (not
        # rebuilding TransactionSplitInput) on purpose: an existing split's
        # category_id can be None if that category was since deleted, and
        # the sum check below needs none of that — only tags/category
        # values that were actually just fetched from the caller could ever
        # need to be re-validated, and those go through payload.splits above.
        split_count = len(transaction.splits)
        split_total = sum((s.amount for s in transaction.splits), Decimal("0")) if transaction.splits else None
    split_violation = split_rule_violation(
        type=effective_type,
        amount=effective_amount,
        category_id=effective_category_id,
        split_count=split_count,
        split_total=split_total,
    )
    if split_violation:
        raise HTTPException(status_code=400, detail=split_violation)

    for field, value in updates.items():
        setattr(transaction, field, value)
    if payload.tag_ids is not None:
        transaction.tags = await _resolve_tags(session, payload.tag_ids)
    if payload.splits is not None:
        transaction.splits = await _build_splits(session, payload.splits, effective_type)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction_id)
    )
    return refreshed.scalar_one()


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, session: AsyncSession = Depends(get_session)) -> None:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await session.delete(transaction)
    await session.commit()
