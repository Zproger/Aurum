from datetime import date as date_
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import RequestWorkspace, get_request_workspace, get_session
from app.core.audit import log_destructive
from app.models.account import Account
from app.models.category import Category
from app.models.enums import CategoryKind, ExchangeRateSource, TransactionType
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
from app.services.categorization_service import category_for_transaction
from app.services.exchange_rate_service import get_exchange_rate

router = APIRouter(prefix="/transactions", tags=["transactions"])

_EAGER = (
    selectinload(Transaction.account),
    selectinload(Transaction.category),
    selectinload(Transaction.splits).selectinload(TransactionSplit.category),
)


def _tag_eager(context: RequestWorkspace):
    # Defense in depth for historical/corrupt links: eager reads must never
    # serialize a foreign tag even if DB integrity was bypassed by an admin.
    tags = Transaction.tags
    if context.workspace_id is not None:
        tags = tags.and_(Tag.workspace_id == context.workspace_id)
    return selectinload(tags)


def _eager(context: RequestWorkspace) -> tuple:
    return (*_EAGER, _tag_eager(context))


async def _resolve_tags(session: AsyncSession, tag_ids: list[int], context: RequestWorkspace) -> list[Tag]:
    if not tag_ids:
        return []
    statement = select(Tag).where(Tag.id.in_(tag_ids))
    if context.workspace_id is not None:
        statement = statement.where(Tag.workspace_id == context.workspace_id)
    result = await session.execute(statement)
    tags = list(result.scalars().all())
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown tag id(s): {sorted(missing)}")
    return tags

_TYPE_TO_CATEGORY_KIND = {
    TransactionType.INCOME: CategoryKind.INCOME,
    TransactionType.EXPENSE: CategoryKind.EXPENSE,
}


async def _currency_fields(
    session: AsyncSession, values: dict, context: RequestWorkspace, current: Transaction | None = None
) -> dict:
    """Resolve account currencies and freeze the KZT conversion snapshot.

    Also resolves the transaction's own currency and the amount in it. A
    transaction isn't forced into its account's currency — paying 5 USD with a
    KZT card is currency="USD", transaction_amount=5, amount=2650 (what the
    account was really debited) — so `currency` falls back to the account's
    and `transaction_amount` to `amount` when the caller leaves them out.

    The caller may submit a manual/CSV rate; otherwise the official NBK rate
    for the transaction date is cached and used. Client-supplied base amounts
    are never trusted because they must remain consistent with amount*rate.
    """
    account_id = values.get("account_id", current.account_id if current else None)
    amount = values.get("amount", current.amount if current else None)
    tx_date = values.get("date", current.date if current else None)
    tx_type = values.get("type", current.type if current else None)
    transfer_account_id = values.get(
        "transfer_account_id", current.transfer_account_id if current else None
    )
    account_stmt = select(Account).where(Account.id == account_id)
    if context.workspace_id is not None:
        account_stmt = account_stmt.where(Account.workspace_id == context.workspace_id)
    account = (await session.execute(account_stmt)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=400, detail="Account not found")

    currency = (values.get("currency") or (current.currency if current else None) or account.currency).upper()
    same_currency = currency == account.currency.upper()
    transaction_amount = values.get("transaction_amount")
    if transaction_amount is None:
        if same_currency:
            # One currency, one number: the two figures can't disagree.
            transaction_amount = amount
        elif current is not None:
            # A foreign-currency row keeps its own figure while only the
            # account-side debit is being edited.
            transaction_amount = current.transaction_amount
        else:
            transaction_amount = amount
    if same_currency and transaction_amount != amount:
        raise HTTPException(
            status_code=422,
            detail="transaction_amount must equal amount when the transaction currency matches the account currency",
        )
    values["currency"] = currency
    values["transaction_amount"] = transaction_amount

    explicit_rate = values.get("exchange_rate_to_kzt")
    if explicit_rate is not None:
        rate = explicit_rate
        source = values.get("exchange_rate_source") or ExchangeRateSource.MANUAL
    elif current is not None and not ({"account_id", "amount", "date"} & values.keys()):
        rate = current.exchange_rate_to_kzt
        source = current.exchange_rate_source
    elif account.currency.upper() == "KZT":
        rate = Decimal("1")
        source = ExchangeRateSource.NBK
    else:
        try:
            official = await get_exchange_rate(session, tx_date, account.currency)
            rate = official.rate_to_kzt
            source = ExchangeRateSource.NBK
        except HTTPException as exc:
            if exc.status_code not in {422, 503}:
                raise
            # Offline entry must remain possible. Cross-currency reports will
            # treat this row as unresolved until /exchange-rates/sync or a
            # manual edit supplies the missing snapshot.
            rate = None
            source = None

    values["exchange_rate_to_kzt"] = rate
    values["base_amount_kzt"] = (amount * rate).quantize(Decimal("0.01")) if rate is not None else None
    values["exchange_rate_source"] = source

    if tx_type == TransactionType.TRANSFER:
        destination_stmt = select(Account).where(Account.id == transfer_account_id)
        if context.workspace_id is not None:
            destination_stmt = destination_stmt.where(Account.workspace_id == context.workspace_id)
        destination = (await session.execute(destination_stmt)).scalar_one_or_none()
        if destination is None:
            raise HTTPException(status_code=400, detail="Transfer account not found")
        supplied = values.get("transfer_amount", current.transfer_amount if current else None)
        if account.currency.upper() == destination.currency.upper():
            if supplied is not None and supplied != amount:
                raise HTTPException(status_code=422, detail="Same-currency transfer_amount must equal amount")
            values["transfer_amount"] = amount
        elif supplied is None:
            raise HTTPException(status_code=422, detail="transfer_amount is required for a cross-currency transfer")
    else:
        values["transfer_amount"] = None
    return values


async def _ensure_category_matches_type(
    session: AsyncSession,
    category_id: int | None,
    transaction_type: TransactionType,
    context: RequestWorkspace,
) -> Category | None:
    """Validate explicit category choices without hiding expense refunds.

    Expenses still require an expense category. Income may use an income
    category or an expense category: the latter is a refund and envelope
    budgeting attributes it back to that category. Automatic categorization
    remains kind-strict, so only an explicit user/import choice creates a
    refund. Returns the fetched row so split validation need not fetch twice.
    """
    if category_id is None:
        return None
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    statement = select(Category).where(Category.id == category_id)
    if context.workspace_id is not None:
        statement = statement.where(Category.workspace_id == context.workspace_id)
    category = (await session.execute(statement)).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    is_expense_refund = transaction_type == TransactionType.INCOME and category.kind == CategoryKind.EXPENSE
    if expected_kind is not None and category.kind != expected_kind and not is_expense_refund:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} transaction",
        )
    return category


async def _build_splits(
    session: AsyncSession,
    splits: list[TransactionSplitInput],
    transaction_type: TransactionType,
    context: RequestWorkspace,
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
        category = await _ensure_category_matches_type(session, split.category_id, transaction_type, context)
        assert category is not None  # split.category_id is required (not Optional) on the schema
        top_level_ids.add(category.parent_id if category.parent_id is not None else category.id)
    if len(top_level_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="All split categories must be the same parent category or its direct subcategories",
        )
    return [
        TransactionSplit(
            category_id=s.category_id, amount=s.amount, note=s.note, workspace_id=context.workspace_id
        )
        for s in splits
    ]


async def _apply_categorization_rule(
    session: AsyncSession, fields: dict, context: RequestWorkspace
) -> None:
    """Fills `category_id` in from the saved rules when the caller left it out.

    Only ever fills a gap — a category the caller chose is never overruled,
    which is the same rule the bulk apply follows. A rule that matches but
    points at a category of the wrong kind is skipped rather than raising: the
    rule was written for something else, and a 400 would block an entry the user
    is otherwise happy with.
    """
    if fields.get("category_id") is not None:
        return
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(fields["type"])
    if expected_kind is None:
        # A transfer carries no category, so there is nothing for a rule to set.
        return
    fields["category_id"] = await category_for_transaction(
        session,
        description=fields.get("description") or "",
        merchant=fields.get("merchant"),
        amount=fields["amount"],
        currency=fields.get("currency") or "",
        account_id=fields["account_id"],
        transaction_type=fields["type"],
        expected_kind=expected_kind,
        context=context,
    )


@router.get("", response_model=TransactionPage)
async def list_transactions(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    account_id: int | None = None,
    # Several accounts at once (the analytics account filter); combines with account_id.
    account_ids: list[int] | None = Query(default=None),
    category_id: int | None = None,
    tag_id: int | None = None,
    type: TransactionType | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=255),
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = Query(default="date_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> TransactionPage:
    stmt = select(Transaction).options(*_eager(context))
    count_stmt = select(func.count()).select_from(Transaction)
    if context.workspace_id is not None:
        stmt = stmt.where(Transaction.workspace_id == context.workspace_id)
        count_stmt = count_stmt.where(Transaction.workspace_id == context.workspace_id)

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
    if account_ids:
        stmt = stmt.where(Transaction.account_id.in_(account_ids))
        count_stmt = count_stmt.where(Transaction.account_id.in_(account_ids))
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
        tag_filter = Tag.id == tag_id
        if context.workspace_id is not None:
            tag_filter = tag_filter & (Tag.workspace_id == context.workspace_id)
        stmt = stmt.where(Transaction.tags.any(tag_filter))
        count_stmt = count_stmt.where(Transaction.tags.any(tag_filter))
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
async def list_transaction_years(
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> list[int]:
    """Full range of years to offer in the year picker — from the earliest
    transaction through the current year, so a gap year with no activity
    still shows up (as zero) instead of silently disappearing from the UI."""
    statement = select(func.min(Transaction.date), func.max(Transaction.date))
    if context.workspace_id is not None:
        statement = statement.where(Transaction.workspace_id == context.workspace_id)
    bounds = await session.execute(statement)
    min_date, max_date = bounds.one()
    current_year = date_.today().year
    if min_date is None:
        return [current_year]
    return list(range(min_date.year, max(max_date.year, current_year) + 1))


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(
    payload: TransactionCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> Transaction:
    context.require_mutation()
    await _ensure_category_matches_type(session, payload.category_id, payload.type, context)
    fields = payload.model_dump(exclude={"tag_ids", "splits"})
    fields = await _currency_fields(session, fields, context)
    # Nobody picked a category — let the saved rules decide, exactly as the
    # import preview does.
    await _apply_categorization_rule(session, fields, context)
    transaction = Transaction(
        **fields, workspace_id=context.workspace_id, author_user_id=context.author_user_id
    )
    transaction.tags = await _resolve_tags(session, payload.tag_ids, context)
    if payload.splits:
        transaction.splits = await _build_splits(session, payload.splits, payload.type, context)
    session.add(transaction)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_eager(context)).where(Transaction.id == transaction.id)
    )
    return refreshed.scalar_one()


@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> TransactionBulkCreateResult:
    """CSV import lands here — see schemas.TransactionBulkCreate. All rows
    are validated before any is added, so a bad row 400s the whole request
    instead of leaving a half-imported statement behind."""
    context.require_mutation()
    for item in payload.items:
        await _ensure_category_matches_type(session, item.category_id, item.type, context)

    transactions = []
    for item in payload.items:
        fields = await _currency_fields(session, item.model_dump(exclude={"tag_ids", "splits"}), context)
        await _apply_categorization_rule(session, fields, context)
        transaction = Transaction(
            **fields, workspace_id=context.workspace_id, author_user_id=context.author_user_id
        )
        transaction.tags = await _resolve_tags(session, item.tag_ids, context)
        if item.splits:
            transaction.splits = await _build_splits(session, item.splits, item.type, context)
        transactions.append(transaction)

    session.add_all(transactions)
    await session.commit()
    # One request can add thousands of rows (CSV import) — worth a line so an
    # unexpected pile of transactions can be dated later.
    log_destructive("transactions.bulk_created", count=len(transactions))
    return TransactionBulkCreateResult(created=len(transactions))


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> Transaction:
    context.require_mutation()
    # Eager-loads tags and splits — assigning transaction.tags/splits below
    # would otherwise lazy-load the current collection first to diff
    # against, which async SQLAlchemy can't do outside an explicit await
    # (MissingGreenlet).
    transaction_stmt = (
        select(Transaction)
        .options(_tag_eager(context), selectinload(Transaction.splits))
        .where(Transaction.id == transaction_id)
    )
    if context.workspace_id is not None:
        transaction_stmt = transaction_stmt.where(Transaction.workspace_id == context.workspace_id)
    transaction = (await session.execute(transaction_stmt)).scalar_one_or_none()
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
    await _ensure_category_matches_type(session, effective_category_id, effective_type, context)
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

    updates = await _currency_fields(session, updates, context, transaction)

    for field, value in updates.items():
        setattr(transaction, field, value)
    if payload.tag_ids is not None:
        transaction.tags = await _resolve_tags(session, payload.tag_ids, context)
    if payload.splits is not None:
        transaction.splits = await _build_splits(session, payload.splits, effective_type, context)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_eager(context)).where(Transaction.id == transaction_id)
    )
    return refreshed.scalar_one()


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
) -> None:
    context.require_mutation()
    statement = select(Transaction).where(Transaction.id == transaction_id)
    if context.workspace_id is not None:
        statement = statement.where(Transaction.workspace_id == context.workspace_id)
    transaction = (await session.execute(statement)).scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await session.delete(transaction)
    await session.commit()
