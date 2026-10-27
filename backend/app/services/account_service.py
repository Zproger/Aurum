"""Account CRUD, plus each account's live balance — summed from its
Transaction rows (income adds, expense subtracts, a transfer moves the
amount from the source account to the destination account) rather than
stored, the same "derive it, don't duplicate it" approach
net_worth_service.py uses for Cash.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.fx_service import money, rate_to_usd


async def _account_balances(session: AsyncSession) -> dict[int, Decimal]:
    result = await session.execute(
        select(Transaction.type, Transaction.account_amount, Transaction.transfer_amount, Transaction.account_id, Transaction.transfer_account_id)
    )
    balances: dict[int, Decimal] = defaultdict(Decimal)
    for tx_type, amount, transfer_amount, account_id, transfer_account_id in result.all():
        if tx_type == TransactionType.INCOME:
            balances[account_id] += amount
        elif tx_type == TransactionType.EXPENSE:
            balances[account_id] -= amount
        elif tx_type == TransactionType.TRANSFER:
            balances[account_id] -= amount
            if transfer_account_id is not None:
                balances[transfer_account_id] += transfer_amount or amount
    return balances


def _to_read(account: Account, balance: Decimal, usd_rate: Decimal = Decimal("1")) -> AccountWithBalance:
    return AccountWithBalance(
        id=account.id,
        name=account.name,
        type=account.type,
        currency=account.currency,
        color=account.color,
        is_archived=account.is_archived,
        balance=balance,
        balance_usd=money(balance * usd_rate),
    )


async def list_accounts(session: AsyncSession, include_archived: bool) -> list[AccountWithBalance]:
    stmt = select(Account).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = (await session.execute(stmt)).scalars().all()
    balances = await _account_balances(session)
    result = []
    for account in accounts:
        balance = balances.get(account.id, Decimal("0"))
        rate = (await rate_to_usd(account.currency, date.today())).rate if balance else Decimal("1")
        result.append(_to_read(account, balance, rate))
    return result


async def create_account(session: AsyncSession, payload: AccountCreate) -> AccountWithBalance:
    account = Account(**payload.model_dump())
    session.add(account)
    await session.commit()
    await session.refresh(account)
    # A brand-new account has no transactions yet — no need to query.
    return _to_read(account, Decimal("0"))


async def update_account(session: AsyncSession, account_id: int, payload: AccountUpdate) -> AccountWithBalance:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.currency is not None and payload.currency != account.currency:
        used = await session.execute(select(Transaction.id).where(
            (Transaction.account_id == account_id) | (Transaction.transfer_account_id == account_id)
        ).limit(1))
        if used.first() is not None:
            raise HTTPException(400, "Cannot change the currency of an account with transactions")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances = await _account_balances(session)
    balance = balances.get(account.id, Decimal("0"))
    rate = (await rate_to_usd(account.currency, date.today())).rate if balance else Decimal("1")
    return _to_read(account, balance, rate)


async def delete_account(session: AsyncSession, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    await session.commit()
