from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssetClass, CapitalRole, RiskLevel


class AssetValuationCreate(BaseModel):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)


class AssetValuationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    value: Decimal
    as_of_date: date_


class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    asset_class: AssetClass
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=2000)
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    # Rough self-reported monthly net cash flow — informational, not tracked
    # transactions (see Asset.monthly_cash_flow).
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel = RiskLevel.MEDIUM


class AssetCreate(AssetBase):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    asset_class: AssetClass | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=2000)
    capital_role: CapitalRole | None = None
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel | None = None


class AssetRead(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_value: Decimal
    as_of_date: date_
