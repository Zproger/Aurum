from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, get_account_filter, get_request_workspace, get_session
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def read_dashboard_summary(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
    account_ids: AccountIds = Depends(get_account_filter),
) -> DashboardSummary:
    return await get_dashboard_summary(session, year, month, context, account_ids)
