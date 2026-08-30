"""Shape of a full-database backup file (see services/backup_service.py)."""
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AccountType,
    AssetClass,
    CapitalRole,
    CategoryKind,
    CryptoTransactionType,
    RecurringFrequency,
    RiskLevel,
    TransactionType,
)


class AccountBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: AccountType
    currency: str
    color: str | None
    is_archived: bool
    zenmoney_id: str | None = None


class CategoryBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    icon: str | None
    color: str
    sort_order: int
    is_default: bool
    # Defaulted so a backup exported before subcategories existed still
    # imports cleanly under the same format version.
    parent_id: int | None = None
    zenmoney_id: str | None = None


class TagBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    date: date_
    # Defaulted so a backup exported before tags existed still imports
    # cleanly under the same format version. Not a plain column — populated
    # explicitly in build_backup() from the `tags` relationship, since
    # from_attributes can't map a `tags` relationship to a `tag_ids` field.
    tag_ids: list[int] = Field(default_factory=list)
    zenmoney_id: str | None = None


class TransactionSplitBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    category_id: int | None
    amount: Decimal
    note: str | None


class AssetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    asset_class: AssetClass
    currency: str
    notes: str | None
    # Defaulted so a backup exported before capital_role/monthly_cash_flow
    # existed still imports cleanly under the same format version.
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    monthly_cash_flow: Decimal | None = None
    # Defaulted so a backup exported before risk_level existed still
    # imports cleanly under the same format version.
    risk_level: RiskLevel = RiskLevel.MEDIUM


class AssetValuationBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    value: Decimal
    as_of_date: date_


class CryptoHoldingBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # asset_id doubles as this row's own primary key (see
    # models/crypto.py's CryptoHolding) — there's no separate `id`. No
    # quantity here — it's derived from crypto_transactions below, not
    # stored.
    asset_id: int
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None
    last_price: Decimal | None = None
    price_change_1h: Decimal | None = None
    price_change_24h: Decimal | None = None
    price_change_7d: Decimal | None = None


class CryptoTransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    type: CryptoTransactionType
    quantity: Decimal
    price_per_unit: Decimal
    date: date_
    note: str | None


class BudgetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    monthly_limit: Decimal


class GoalBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_amount: Decimal
    target_date: date_ | None


class GoalContributionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    amount: Decimal
    date: date_
    note: str | None


class RecurringTransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    frequency: RecurringFrequency
    anchor_date: date_
    last_posted_date: date_ | None
    is_active: bool


class AppSettingsBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    # Defaulted so a backup exported before these thresholds existed still
    # imports cleanly under the same format version.
    negative_cash_flow_threshold_months: int = 2
    net_worth_decline_threshold_months: int = 2
    # Defaulted so a backup exported before this threshold existed still
    # imports cleanly under the same format version.
    risky_allocation_threshold_percent: int = 20
    # Defaulted so a backup exported before idle-cash thresholds existed
    # still imports cleanly under the same format version.
    idle_cash_threshold_amount: Decimal = Decimal("1000")
    idle_cash_threshold_days: int = 60


class BackupPayload(BaseModel):
    """A full, portable snapshot of every table. `aurum_backup_version` is
    checked on import so an incompatible/future file is rejected cleanly
    instead of half-applied."""

    aurum_backup_version: int
    exported_at: datetime
    app_version: str
    accounts: list[AccountBackup]
    categories: list[CategoryBackup]
    # Defaulted so a backup exported before tags existed still imports
    # cleanly under the same format version.
    tags: list[TagBackup] = Field(default_factory=list)
    transactions: list[TransactionBackup]
    # Defaulted so a backup exported before transaction splitting existed
    # still imports cleanly under the same format version.
    transaction_splits: list[TransactionSplitBackup] = Field(default_factory=list)
    assets: list[AssetBackup]
    asset_valuations: list[AssetValuationBackup]
    # Defaulted so a backup exported before crypto holdings existed still
    # imports cleanly under the same format version.
    crypto_holdings: list[CryptoHoldingBackup] = Field(default_factory=list)
    crypto_transactions: list[CryptoTransactionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before budgets existed still imports
    # cleanly under the same format version.
    budgets: list[BudgetBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before goals existed still imports
    # cleanly under the same format version.
    goals: list[GoalBackup] = Field(default_factory=list)
    goal_contributions: list[GoalContributionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before recurring transactions existed
    # still imports cleanly under the same format version.
    recurring_transactions: list[RecurringTransactionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before the currency setting existed
    # still imports cleanly under the same format version.
    app_settings: AppSettingsBackup = Field(default_factory=lambda: AppSettingsBackup(currency="USD"))
