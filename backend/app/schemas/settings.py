from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import APP_VERSION


class AppSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    negative_cash_flow_threshold_months: int
    net_worth_decline_threshold_months: int
    risky_allocation_threshold_percent: int
    idle_cash_threshold_amount: Decimal
    idle_cash_threshold_days: int
    # Not a stored column: the default fills itself in when FastAPI validates
    # the ORM row against this model, so neither route has to assemble it.
    # It lives on this (authenticated) response rather than on /api/health,
    # which is deliberately unauthenticated and so would hand the running
    # version to anyone who can reach the instance.
    app_version: str = APP_VERSION


class AppSettingsUpdate(BaseModel):
    """All fields optional — the route applies a partial update
    (`exclude_unset`), same as CategoryUpdate, so a single-field PATCH from
    e.g. CurrencyCard doesn't need to resend the alert thresholds."""

    # All aggregated figures are denominated in USD.
    currency: Literal["USD"] | None = None
    # Consecutive complete months before the corresponding alert fires.
    # Capped at 24 to match insights_service.py's MAX_LOOKBACK_MONTHS.
    negative_cash_flow_threshold_months: int | None = Field(default=None, ge=1, le=24)
    net_worth_decline_threshold_months: int | None = Field(default=None, ge=1, le=24)
    # Max % of capital allowed in medium/high risk tiers (the 80/20 rule's
    # "20% at most exposed" half) before risky_allocation_exceeded fires.
    risky_allocation_threshold_percent: int | None = Field(default=None, ge=1, le=100)
    # Balance (in the app's display currency) and days of no activity a
    # depository account needs to hit before idle_cash fires.
    idle_cash_threshold_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    idle_cash_threshold_days: int | None = Field(default=None, ge=1, le=365)
