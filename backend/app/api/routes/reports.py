from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.enums import CategoryKind
from app.schemas.reports import (
    CategoryRankingReport,
    CategorySpendingReport,
    TagRankingReport,
    TagSpendingReport,
)
from app.services.reports_service import (
    get_category_ranking_report,
    get_category_spending_report,
    get_tag_ranking_report,
    get_tag_spending_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/category-spending", response_model=CategorySpendingReport)
async def read_category_spending_report(
    category_id: int,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CategorySpendingReport:
    return await get_category_spending_report(session, category_id, start_date, end_date)


@router.get("/category-ranking", response_model=CategoryRankingReport)
async def read_category_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CategoryRankingReport:
    return await get_category_ranking_report(session, kind, start_date, end_date)


@router.get("/tag-ranking", response_model=TagRankingReport)
async def read_tag_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> TagRankingReport:
    return await get_tag_ranking_report(session, kind, start_date, end_date)


@router.get("/tag-spending", response_model=TagSpendingReport)
async def read_tag_spending_report(
    tag_id: int,
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> TagSpendingReport:
    return await get_tag_spending_report(session, tag_id, kind, start_date, end_date)
