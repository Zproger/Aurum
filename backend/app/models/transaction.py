"""A single money movement: income, expense, or a transfer between accounts."""
from datetime import date as date_

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TransactionType
from app.models.mixins import TimestampMixin
from app.models.tag import transaction_tags


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Destination account for TRANSFER-type rows only.
    transfer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=False, length=10), nullable=False
    )
    # Always stored positive; `type` carries the sign/direction.
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    # Optional ZenMoney transaction UUID for automatic sync/deduplication.
    zenmoney_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)

    account: Mapped["Account"] = relationship(back_populates="transactions", foreign_keys=[account_id])
    transfer_account: Mapped["Account | None"] = relationship(foreign_keys=[transfer_account_id])
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    tags: Mapped[list["Tag"]] = relationship(secondary=transaction_tags, back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionSplit.id"
    )


class TransactionSplit(Base):
    """One category's slice of a transaction whose amount is divided across
    several categories (one receipt, several kinds of goods) — an
    alternative to Transaction.category_id, not an addition to it: a split
    transaction has category_id=NULL and two or more of these instead, and
    their amounts must add up to the parent's amount exactly (see
    schemas/transaction.py's split_rule_violation).

    category_id is nullable + SET NULL, same as Transaction.category_id
    itself — deleting a category must not break *reading* a split that used
    to point at it, only creating/editing one requires a live category (see
    routes/transactions.py, and the same lesson already applied to
    transfer_account_id)."""

    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="splits")
    category: Mapped["Category | None"] = relationship()
