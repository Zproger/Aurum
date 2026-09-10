from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.core.text import capitalize_first_letter
from app.models.enums import RecurringFrequency, TransactionType


class RecurringTransactionCreate(BaseModel):
    account_id: int
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=1, max_length=255)
    merchant: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    frequency: RecurringFrequency
    anchor_date: date_

    # Keeps templates consistent with regular transactions — see
    # app/schemas/transaction.py for the same rule.
    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str) -> str:
        return capitalize_first_letter(value)


class RecurringTransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    merchant: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    frequency: RecurringFrequency | None = None
    anchor_date: date_ | None = None
    is_active: bool | None = None

    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str | None) -> str | None:
        return capitalize_first_letter(value) if value is not None else None


class RecurringTransactionRead(BaseModel):
    id: int
    account_id: int
    account_name: str
    category_id: int | None
    category_name: str | None
    category_color: str | None
    category_icon: str | None
    transfer_account_id: int | None
    transfer_account_name: str | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    frequency: RecurringFrequency
    anchor_date: date_
    last_posted_date: date_ | None
    is_active: bool
    # Computed, not stored — see services/recurring_service.py.
    next_due_date: date_
    is_due: bool
    days_until_due: int
