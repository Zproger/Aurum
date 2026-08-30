"""ZenMoney synchronization state and metadata."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ZenmoneySyncState(Base):
    """Singleton row (id=1, same pattern as AppSettings/CryptoSyncState)
    tracking the diff timestamp and statistics of the last ZenMoney sync.
    """

    __tablename__ = "zenmoney_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_accounts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_categories_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_transactions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
