"""Recurring transaction templates: CRUD, plus "post now" — a one-click
action that creates a real Transaction from the template. Deliberately not a
background job (see also insights_service.py's docstring on scope): the
schedule only advances when the user actually clicks Post, so a missed
week never silently back-fills a pile of transactions.
"""
import calendar
from datetime import date as date_
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.account import Account
from app.models.enums import CategoryKind, RecurringFrequency, TransactionType
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.schemas.recurring import RecurringTransactionCreate, RecurringTransactionRead, RecurringTransactionUpdate
from app.services.fx_service import booked_amounts

_EAGER = (
    selectinload(RecurringTransaction.account),
    selectinload(RecurringTransaction.category),
    selectinload(RecurringTransaction.transfer_account),
)

_TYPE_TO_CATEGORY_KIND = {
    TransactionType.INCOME: CategoryKind.INCOME,
    TransactionType.EXPENSE: CategoryKind.EXPENSE,
}


async def _ensure_category_matches_type(
    session: AsyncSession, category_id: int | None, transaction_type: TransactionType
) -> None:
    if category_id is None:
        return
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} recurring transaction",
        )


def _advance(day: date_, frequency: RecurringFrequency) -> date_:
    if frequency == RecurringFrequency.WEEKLY:
        return day + timedelta(days=7)
    if frequency == RecurringFrequency.MONTHLY:
        year = day.year + (day.month // 12)
        month = day.month % 12 + 1
        clamped_day = min(day.day, calendar.monthrange(year, month)[1])
        return date_(year, month, clamped_day)
    # YEARLY — Feb 29 anchors fall back to Feb 28 in non-leap years.
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def _next_due_date(recurring: RecurringTransaction) -> date_:
    if recurring.last_posted_date is None:
        return recurring.anchor_date
    return _advance(recurring.last_posted_date, recurring.frequency)


def _to_read(recurring: RecurringTransaction) -> RecurringTransactionRead:
    next_due = _next_due_date(recurring)
    today = date_.today()
    return RecurringTransactionRead(
        id=recurring.id,
        account_id=recurring.account_id,
        account_name=recurring.account.name,
        category_id=recurring.category_id,
        category_name=recurring.category.name if recurring.category else None,
        category_color=recurring.category.color if recurring.category else None,
        category_icon=recurring.category.icon if recurring.category else None,
        transfer_account_id=recurring.transfer_account_id,
        transfer_account_name=recurring.transfer_account.name if recurring.transfer_account else None,
        type=recurring.type,
        amount=recurring.amount,
        currency=recurring.currency,
        description=recurring.description,
        merchant=recurring.merchant,
        notes=recurring.notes,
        frequency=recurring.frequency,
        anchor_date=recurring.anchor_date,
        last_posted_date=recurring.last_posted_date,
        is_active=recurring.is_active,
        next_due_date=next_due,
        is_due=recurring.is_active and next_due <= today,
        days_until_due=(next_due - today).days,
    )


async def _get_or_404(session: AsyncSession, recurring_id: int) -> RecurringTransaction:
    result = await session.execute(
        select(RecurringTransaction).options(*_EAGER).where(RecurringTransaction.id == recurring_id)
    )
    recurring = result.scalar_one_or_none()
    if recurring is None:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    return recurring


async def list_recurring(session: AsyncSession) -> list[RecurringTransactionRead]:
    result = await session.execute(
        select(RecurringTransaction).options(*_EAGER).order_by(RecurringTransaction.id)
    )
    return [_to_read(row) for row in result.scalars().all()]


async def create_recurring(session: AsyncSession, payload: RecurringTransactionCreate) -> RecurringTransactionRead:
    await _ensure_category_matches_type(session, payload.category_id, payload.type)
    account = await session.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(400, "Account not found")
    fields = payload.model_dump(exclude={"currency"})
    recurring = RecurringTransaction(**fields, currency=payload.currency or account.currency)
    session.add(recurring)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring.id))


async def update_recurring(
    session: AsyncSession, recurring_id: int, payload: RecurringTransactionUpdate
) -> RecurringTransactionRead:
    recurring = await _get_or_404(session, recurring_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("currency", "valid") is None:
        raise HTTPException(400, "Currency is required")
    effective_type = updates.get("type", recurring.type)
    effective_category_id = updates.get("category_id", recurring.category_id)
    await _ensure_category_matches_type(session, effective_category_id, effective_type)
    for field, value in updates.items():
        setattr(recurring, field, value)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id))


async def delete_recurring(session: AsyncSession, recurring_id: int) -> None:
    recurring = await session.get(RecurringTransaction, recurring_id)
    if recurring is None:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    await session.delete(recurring)
    await session.commit()


async def post_recurring(session: AsyncSession, recurring_id: int) -> RecurringTransactionRead:
    """Creates a real Transaction from the template, dated today, and moves
    last_posted_date forward — the only thing that advances the schedule."""
    recurring = await _get_or_404(session, recurring_id)
    today = date_.today()
    account = await session.get(Account, recurring.account_id)
    if account is None:
        raise HTTPException(400, "Account not found")
    destination = await session.get(Account, recurring.transfer_account_id) if recurring.transfer_account_id else None
    if recurring.transfer_account_id and destination is None:
        raise HTTPException(400, "Transfer account not found")
    conversion = await booked_amounts(
        recurring.amount, recurring.currency, account.currency,
        destination.currency if destination else None, today,
    )

    session.add(
        Transaction(
            account_id=recurring.account_id,
            category_id=recurring.category_id,
            transfer_account_id=recurring.transfer_account_id,
            type=recurring.type,
            amount=recurring.amount,
            currency=recurring.currency,
            **conversion,
            description=recurring.description,
            merchant=recurring.merchant,
            notes=recurring.notes,
            date=today,
        )
    )
    recurring.last_posted_date = today
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id))
