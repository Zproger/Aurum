"""An account is any place money lives: bank account, card, cash, wallet."""
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccountType
from app.models.mixins import TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", native_enum=False, length=20),
        nullable=False,
        default=AccountType.CHECKING,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Hex color used for account-scoped UI accents (e.g. transaction list avatars).
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Optional ZenMoney account UUID for automatic sync/deduplication.
    zenmoney_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        foreign_keys="Transaction.account_id",
        cascade="all, delete-orphan",
    )
