"""Daily reference FX rates used when a money movement is posted."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import httpx
from fastapi import HTTPException

_API = "https://api.frankfurter.dev/v2/rate"
_cache: dict[tuple[str, date], tuple["FxQuote", datetime]] = {}
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class FxQuote:
    rate: Decimal  # USD for one unit of the source currency
    date: date


def money(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


async def rate_to_usd(currency: str, on_date: date) -> FxQuote:
    if currency == "USD":
        return FxQuote(Decimal("1"), on_date)
    if on_date > date.today():
        raise HTTPException(400, "Cannot fetch an exchange rate for a future date")

    key = (currency, on_date)
    now = datetime.now(timezone.utc)
    cached = _cache.get(key)
    # Historical observations are immutable for the purposes of a posted
    # transaction. Refresh today's latest observation periodically.
    if cached and (on_date < date.today() or now - cached[1] < timedelta(hours=1)):
        return cached[0]

    url = f"{_API}/{currency.lower()}/usd"
    params = None
    if on_date < date.today():
        # The single-pair historical route 404s on weekends. The rates
        # endpoint carries the last available observation forward.
        url = "https://api.frankfurter.dev/v2/rates"
        params = {"date": on_date.isoformat(), "base": currency.lower(), "quotes": "usd"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, params=params)
            if response.status_code in (404, 422):
                raise HTTPException(400, f"Unsupported exchange rate for {currency}/USD on {on_date}")
            response.raise_for_status()
            data = response.json()
        if isinstance(data, list):
            data = next((row for row in data if row.get("quote", "").upper() == "USD"), None)
            if data is None:
                raise ValueError("rate missing")
        rate = Decimal(str(data["rate"]))
        observed = date.fromisoformat(data["date"])
        if rate <= 0 or observed > on_date:
            raise ValueError("invalid rate or observation date")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        if cached:
            return cached[0]
        raise HTTPException(503, f"Exchange rate unavailable for {currency}/USD on {on_date}") from exc

    quote = FxQuote(rate, observed)
    _cache[key] = (quote, now)
    return quote


async def booked_amounts(
    amount: Decimal, currency: str, account_currency: str,
    transfer_currency: str | None, on_date: date,
) -> dict[str, Decimal | date | None]:
    source = await rate_to_usd(currency, on_date)
    account = await rate_to_usd(account_currency, on_date)
    usd = money(amount * source.rate)
    # Convert from the unrounded USD intermediate so a low-value currency
    # does not lose its entire value before account booking.
    account_amount = money(amount * source.rate / account.rate)
    destination_amount = None
    if transfer_currency is not None:
        destination = await rate_to_usd(transfer_currency, on_date)
        destination_amount = money(amount * source.rate / destination.rate)
    return {
        "fx_rate_to_usd": source.rate,
        "fx_rate_date": source.date,
        "amount_usd": usd,
        "account_amount": account_amount,
        "transfer_amount": destination_amount,
    }
