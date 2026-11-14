"""Month-by-month income vs. expense — the multi-month view neither the
Dashboard (locked to one month) nor Reports (one category at a time, or a
category ranking) answers on its own. Transfers between the user's own
accounts are excluded from both totals, same as the Dashboard breakdown.
"""
from collections import defaultdict
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, filter_accounts, scope_to_workspace
from app.models.enums import TransactionPurpose, TransactionType
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.cash_flow import CashFlowPoint, CashFlowResponse
from app.services.currency import transaction_amount_kzt
from app.services.reporting_currency import reporting_converter


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def get_cash_flow(
    session: AsyncSession,
    start_date: date_ | None,
    end_date: date_ | None,
    context: RequestWorkspace,
    account_ids: AccountIds = None,
) -> CashFlowResponse:
    bounds_stmt = scope_to_workspace(
        select(func.min(Transaction.date), func.max(Transaction.date)), Transaction, context
    ).where(
        Transaction.type != TransactionType.TRANSFER,
        Transaction.purpose != TransactionPurpose.INVESTMENT_TRADE,
    )
    bounds_stmt = filter_accounts(bounds_stmt, Transaction.account_id, account_ids)
    if start_date:
        bounds_stmt = bounds_stmt.where(Transaction.date >= start_date)
    if end_date:
        bounds_stmt = bounds_stmt.where(Transaction.date <= end_date)
    min_date, max_date = (await session.execute(bounds_stmt)).one()

    effective_start = start_date or min_date
    effective_end = end_date or max_date
    converter = await reporting_converter(session, context.workspace_id)

    empty = CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        reporting_currency=converter.currency,
        points=[],
        total_income=Decimal("0"),
        total_expense=Decimal("0"),
        total_net=Decimal("0"),
    )
    if effective_start is None or effective_end is None:
        return empty

    rows_stmt = scope_to_workspace(
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            Transaction.type,
            func.sum(transaction_amount_kzt()).label("amount"),
        )
        .join(Account, Account.id == Transaction.account_id),
        Transaction,
        context,
    )
    rows_stmt = scope_to_workspace(rows_stmt, Account, context).where(
        Transaction.type != TransactionType.TRANSFER,
        Transaction.purpose != TransactionPurpose.INVESTMENT_TRADE,
        Transaction.date >= effective_start,
        Transaction.date <= effective_end,
    ).group_by("year", "month", Transaction.type)
    rows_stmt = filter_accounts(rows_stmt, Transaction.account_id, account_ids)
    rows = (await session.execute(rows_stmt)).all()

    by_month: dict[tuple[int, int], dict[TransactionType, Decimal]] = defaultdict(dict)
    for year, month, tx_type, amount in rows:
        by_month[(int(year), int(month))][tx_type] = amount

    points: list[CashFlowPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        totals = by_month.get((year, month), {})
        # Summed in KZT, converted once per month at that month's end rate.
        income = await converter.convert_month(totals.get(TransactionType.INCOME, Decimal("0")), year, month)
        expense = await converter.convert_month(totals.get(TransactionType.EXPENSE, Decimal("0")), year, month)
        net = income - expense if income is not None and expense is not None else None
        points.append(CashFlowPoint(year=year, month=month, income=income, expense=expense, net=net))
        year, month = _next_month(year, month)

    total_income = sum((p.income for p in points if p.income is not None), Decimal("0"))
    total_expense = sum((p.expense for p in points if p.expense is not None), Decimal("0"))
    await converter.commit_fetched()

    return CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        reporting_currency=converter.currency,
        incomplete=converter.incomplete,
        points=points,
        total_income=total_income,
        total_expense=total_expense,
        total_net=total_income - total_expense,
    )
