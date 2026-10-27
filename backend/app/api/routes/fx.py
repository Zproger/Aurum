"""Preview the daily reference rate used for fiat money entries."""
from datetime import date as date_
from decimal import Decimal

from fastapi import APIRouter, Query

from app.services.fx_service import rate_to_usd

router = APIRouter(prefix="/fx", tags=["fx"])


@router.get("/quote")
async def read_fx_quote(
    currency: str = Query(pattern=r"^[A-Z]{3}$"),
    date: date_ = Query(),
) -> dict:
    quote = await rate_to_usd(currency, date)
    return {"currency": currency, "rate_to_usd": quote.rate, "rate_date": quote.date}
