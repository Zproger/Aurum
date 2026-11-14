from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountIds, RequestWorkspace, get_account_filter, get_request_workspace, get_session
from app.schemas.cash_flow import CashFlowResponse
from app.services.cash_flow_service import get_cash_flow

router = APIRouter(prefix="/cash-flow", tags=["cash-flow"])


@router.get("", response_model=CashFlowResponse)
async def read_cash_flow(
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    context: RequestWorkspace = Depends(get_request_workspace),
    account_ids: AccountIds = Depends(get_account_filter),
) -> CashFlowResponse:
    return await get_cash_flow(session, start_date, end_date, context, account_ids)
