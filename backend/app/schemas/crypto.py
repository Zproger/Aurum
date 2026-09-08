from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CryptoTransactionType, RiskLevel


class CryptoTransactionCreate(BaseModel):
    type: CryptoTransactionType
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    # Price paid (buy) / received (sell) per unit, in the app's display
    # currency — not fetched from CoinGecko, this is what the user actually
    # paid, which the market price today has nothing to do with.
    price_per_unit: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    date: date_
    note: str | None = Field(default=None, max_length=500)


class CryptoTransactionUpdate(BaseModel):
    type: CryptoTransactionType | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=38, decimal_places=18)
    price_per_unit: Decimal | None = Field(default=None, gt=0, max_digits=38, decimal_places=18)
    date: date_ | None = None
    note: str | None = Field(default=None, max_length=500)


class CryptoTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    type: CryptoTransactionType
    quantity: Decimal
    price_per_unit: Decimal
    date: date_
    note: str | None


class CryptoPortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CryptoPortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_archived: bool | None = None


class CryptoPortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    is_archived: bool


class CryptoHoldingCreate(BaseModel):
    # Which portfolio to file this coin under — omit to use the default
    # portfolio (the earliest-created one, auto-created if none exists yet;
    # see services/crypto_service.py's get_or_create_default_portfolio).
    portfolio_id: int | None = None
    coingecko_id: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    thumb_url: str | None = Field(default=None, max_length=500)
    # A holding always starts with a buy — there's nothing to "start
    # tracking" with a sell.
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    price_per_unit: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    date: date_ = Field(default_factory=date_.today)
    note: str | None = Field(default=None, max_length=500)
    # Defaults to HIGH — crypto is this app's textbook HIGH example (see
    # services/crypto_service.py) — but user-overridable at add time, since
    # not every coin carries the same risk (a large-cap vs. a memecoin).
    risk_level: RiskLevel = RiskLevel.HIGH


class CryptoHoldingRead(BaseModel):
    asset_id: int
    portfolio_id: int
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None
    # Lives on the underlying Asset (see services/crypto_service.py's
    # _to_read) — editable via the existing PATCH /assets/{asset_id},
    # same endpoint every other Asset already uses, no crypto-specific
    # update route needed.
    risk_level: RiskLevel

    # Quantity and avg_buy_price are derived from the transaction log (see
    # services/crypto_service.py's _compute_position) — never stored.
    quantity: Decimal
    avg_buy_price: Decimal | None

    # Cached from the last successful CoinGecko sync — null until the
    # first one completes.
    current_price: Decimal | None
    price_change_1h: Decimal | None
    price_change_24h: Decimal | None
    price_change_7d: Decimal | None
    price_change_30d: Decimal | None
    # Stands in for "all time" on the Best/Worst Performer stat — CoinGecko's
    # free tier caps historical lookback at 365 days regardless (see
    # services/crypto_service.py's module docstring).
    price_change_1y: Decimal | None

    # All derived from the above: value = current_price * quantity,
    # cost_basis = avg_buy_price * quantity, profit_loss = value - cost_basis.
    value: Decimal | None
    cost_basis: Decimal | None
    profit_loss: Decimal | None
    profit_loss_percent: float | None


class CryptoPerformancePoint(BaseModel):
    asset_id: int
    # None when CoinGecko's 90-day chart couldn't be fetched for this coin
    # (rate-limited, unreachable, or the coin simply lacks 90 days of
    # history) — the item is still listed so the frontend can render "—"
    # for that one coin instead of the whole tile disappearing.
    price_change_percent: float | None


class CryptoPerformanceResponse(BaseModel):
    """Real 90-day % price change per currently-held coin, for the Crypto
    tab's Best/Worst Performer stat when the 90d range is selected — the one
    window CoinGecko's batched /coins/markets call can't give us (see
    services/crypto_service.py's get_90d_performance), so this is fetched
    on demand, once, only when a viewer actually picks 90d."""

    items: list[CryptoPerformancePoint]


class CryptoSyncResult(BaseModel):
    # False when the lazy daily check ran but the 24h window hadn't
    # elapsed yet (nothing called CoinGecko this time, error_key is None),
    # OR when a refresh was attempted but CoinGecko couldn't be reached
    # (error_key is set) — check error_key to tell the two apart. Either
    # way `holdings` still carries the best data on hand, never blocked by
    # an external outage.
    #
    # A key, not a message string: the frontend translates it (RU/EN), same
    # key+params convention as FinancialAlert/AdviceItem — a raw English
    # sentence here would silently break the app's bilingual UI.
    synced: bool
    last_synced_at: datetime | None
    error_key: Literal["unreachable"] | None = None
    holdings: list[CryptoHoldingRead]


class CryptoSearchResult(BaseModel):
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None


class CryptoHistoryPoint(BaseModel):
    date: date_
    value: Decimal


class CryptoHistoryResponse(BaseModel):
    """Total crypto holdings value over time — same "cumulative point
    events, forward-filled" shape as NetWorthSummary's own series, but
    scoped to crypto-class assets only (see services/crypto_service.py's
    get_crypto_history). Powers the History chart on the Crypto tab."""

    range: str
    current: Decimal
    change_amount: Decimal
    change_percent: float | None
    series: list[CryptoHistoryPoint]
