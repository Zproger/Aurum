"""Schemas for ZenMoney synchronization status and actions."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ZenmoneyStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_configured: bool = Field(
        description="True if AURUM_ZENMONEY_TOKEN is set in the environment."
    )
    server_timestamp: int = Field(
        default=0,
        description="Latest diff timestamp returned by the ZenMoney server.",
    )
    last_synced_at: datetime | None = Field(
        default=None,
        description="UTC datetime when the last synchronization completed.",
    )
    synced_accounts_count: int = Field(default=0)
    synced_categories_count: int = Field(default=0)
    synced_transactions_count: int = Field(default=0)
    last_error: str | None = Field(
        default=None,
        description="Error message from the last failed sync attempt, if any.",
    )


class ZenmoneySyncRequest(BaseModel):
    force_full: bool = Field(
        default=False,
        description="If True, resets the server diff timestamp to 0 to re-sync all history from scratch.",
    )


class ZenmoneySyncResult(BaseModel):
    success: bool
    message: str
    server_timestamp: int
    accounts_synced: int
    categories_synced: int
    transactions_synced: int
    transactions_deleted: int
    last_synced_at: datetime
