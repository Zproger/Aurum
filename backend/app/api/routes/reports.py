from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, get_account_filter, get_request_workspace, get_session
from app.models.enums import CategoryKind
from app.schemas.reports import CategoryRankingReport, CategorySpendingReport
from app.services.reports_service import get_category_ranking_report, get_category_spending_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/category-spending", response_model=CategorySpendingReport)
async def read_category_spending_report(
    category_id: int,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
    account_ids: AccountIds = Depends(get_account_filter),
) -> CategorySpendingReport:
    return await get_category_spending_report(session, category_id, start_date, end_date, context, account_ids)


@router.get("/category-ranking", response_model=CategoryRankingReport)
async def read_category_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
    account_ids: AccountIds = Depends(get_account_filter),
) -> CategoryRankingReport:
    return await get_category_ranking_report(session, kind, start_date, end_date, context, account_ids)
