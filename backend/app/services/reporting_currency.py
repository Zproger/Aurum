"""KZT aggregates expressed in a workspace's reporting currency.

Every ledger aggregate (income, spending, cash flow, net worth, budgets,
envelopes, advice) is summed in KZT — `Transaction.base_amount_kzt` and
`AssetValuation.base_value_kzt` are the one currency every row shares, because
the official NBK rates are quoted in it. The workspace, however, reports in
`AppSettings.currency`, and the frontend labels every aggregate with that
currency. This module is the single place a KZT total crosses over into the
reporting currency, so no service has to know how rates are looked up.

Rules:
- KZT reporting is the identity: amounts pass through untouched, no lookup.
- A total is converted once, after summing in KZT (never row by row), at the
  official rate for the *end of its period* — the last day of the month for a
  monthly sum, the point's own date for a timeline. A period ending in the
  future uses today's rate.
- The rate is the cached official one effective on that day: the latest cached
  rate on or before it, else the nearest later one, else — only when nothing is
  cached for the currency at all — one short, bounded NBK request. Same
  approach as dashboard_service._rate_to_kzt (the "Total balance" card), so a
  page load never waits on NBK when a rate is already known.
- No rate at all means no number: `convert` returns None and the converter
  remembers that the answer is `incomplete`, so the caller can say so instead
  of presenting a KZT sum as if it were the reporting currency.
"""
from __future__ import annotations

import bisect
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.exchange_rate import ExchangeRate
from app.models.settings import AppSettings
from app.services.exchange_rate_service import get_exchange_rate

MONEY_QUANT = Decimal("0.01")
# Same bound dashboard_service uses for its cold attempt: a currency with
# nothing cached gets one short try, never a long wait.
COLD_RATE_TIMEOUT_SECONDS = 3.0


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class CachedRate:
    requested_date: date
    rate_to_kzt: Decimal


def pick_cached_rate(
    rates: list[CachedRate], as_of: date, keys: list[date] | None = None
) -> CachedRate | None:
    """The cached rate for `as_of` from rows sorted by requested_date: the
    latest on or before it, else the nearest later one (a later official rate
    is still a real rate), else None. `keys` (the rows' requested_date list)
    can be passed in so a long timeline does not rebuild it per point."""
    if not rates:
        return None
    if keys is None:
        keys = [row.requested_date for row in rates]
    index = bisect.bisect_right(keys, as_of)
    if index > 0:
        return rates[index - 1]
    return rates[0]


def kzt_to_reporting(amount_kzt: Decimal, rate_to_kzt: Decimal) -> Decimal:
    """`rate_to_kzt` is KZT per one unit of the reporting currency."""
    return (Decimal(amount_kzt) / rate_to_kzt).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


class ReportingConverter:
    """Converts KZT totals for one request; caches rate lookups for its
    lifetime, so a 5-year daily timeline costs one query, not 1800."""

    def __init__(self, session: AsyncSession, reporting_currency: str, *, today: date | None = None):
        self.session = session
        self.currency = reporting_currency.upper()
        self.is_identity = self.currency == "KZT"
        self.today = today or date.today()
        # True once any conversion this request needed had no rate at all.
        self.incomplete = False
        # True when a cold NBK lookup cached a new row the caller may commit.
        self.fetched = False
        self._rates: list[CachedRate] | None = None
        self._keys: list[date] = []
        self._cold_attempted = False

    async def _load_rates(self) -> list[CachedRate]:
        if self._rates is None:
            rows = (
                await self.session.execute(
                    select(ExchangeRate.requested_date, ExchangeRate.rate_to_kzt)
                    .where(ExchangeRate.currency == self.currency)
                    .order_by(ExchangeRate.requested_date)
                )
            ).all()
            self._set_rates([CachedRate(row[0], row[1]) for row in rows if row[1]])
        return self._rates

    def _set_rates(self, rates: list[CachedRate]) -> None:
        self._rates = rates
        self._keys = [row.requested_date for row in rates]

    async def rate(self, as_of: date) -> Decimal | None:
        """KZT per one unit of the reporting currency for a period ending
        `as_of` (clamped to today), or None when no rate could be found."""
        if self.is_identity:
            return Decimal("1")
        as_of = min(as_of, self.today)
        rates = await self._load_rates()
        cached = pick_cached_rate(rates, as_of, self._keys)
        if cached is not None:
            return cached.rate_to_kzt
        if self._cold_attempted:
            return None
        self._cold_attempted = True
        try:
            row = await get_exchange_rate(self.session, as_of, self.currency, timeout=COLD_RATE_TIMEOUT_SECONDS)
        except HTTPException:
            return None
        if not row.rate_to_kzt:
            return None
        self.fetched = True
        self._set_rates([CachedRate(row.requested_date, row.rate_to_kzt)])
        return row.rate_to_kzt

    async def convert(self, amount_kzt: Decimal | None, as_of: date) -> Decimal | None:
        """One KZT total in the reporting currency, rounded to 0.01.

        None in, None out (nothing to convert, nothing is flagged). Zero is zero
        in every currency and needs no rate."""
        if amount_kzt is None:
            return None
        if self.is_identity:
            return amount_kzt
        if amount_kzt == 0:
            return Decimal("0.00")
        rate = await self.rate(as_of)
        if rate is None:
            self.incomplete = True
            return None
        return kzt_to_reporting(amount_kzt, rate)

    async def convert_month(self, amount_kzt: Decimal | None, year: int, month: int) -> Decimal | None:
        return await self.convert(amount_kzt, month_end(year, month))

    async def commit_fetched(self) -> None:
        """Persist a freshly fetched official rate. A GET may do this — it is
        the same cache write the /exchange-rates route makes."""
        if self.fetched:
            await self.session.commit()
            self.fetched = False


def _unsaved_settings_currency() -> str:
    """The currency a workspace's settings row gets when
    settings_service.get_or_create_app_settings has to create it: the
    configured AURUM_DEFAULT_CURRENCY (no longer the USD column default). A
    workspace without a row yet reports in that currency the moment any page
    creates it, so a read before then must agree."""
    return get_settings().default_currency.strip().upper() or "KZT"


async def reporting_currency_for(session: AsyncSession, workspace_id: UUID | None) -> str:
    """The workspace's reporting currency, read without creating anything.

    ``None`` is the legacy auth-disabled namespace (the id=1 row), the same
    rule settings_service.get_or_create_app_settings follows."""
    if workspace_id is None:
        settings = await session.get(AppSettings, 1)
        currency = settings.currency if settings is not None else None
    else:
        currency = (
            await session.execute(select(AppSettings.currency).where(AppSettings.workspace_id == workspace_id))
        ).scalar_one_or_none()
    return (currency or _unsaved_settings_currency()).upper()


async def reporting_converter(
    session: AsyncSession, workspace_id: UUID | None, *, today: date | None = None
) -> ReportingConverter:
    return ReportingConverter(session, await reporting_currency_for(session, workspace_id), today=today)
