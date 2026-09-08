"""Crypto holdings: a thin layer on top of the existing Asset/AssetValuation
engine (see models/asset.py) rather than a parallel system. Net worth's
number for a holding still lives as ordinary AssetValuation rows, kept
current by services/crypto_service.py — Net Worth requires zero changes to
treat a crypto holding like any other manually tracked asset.

Quantity and average buy price are NOT stored — they're computed from the
CryptoTransaction log (same "you record it, we derive it" shape as
Goal/GoalContribution), because a sell doesn't just subtract quantity, it
also has to leave the average cost basis of what's still held unchanged
(see services/crypto_service.py's _compute_position).

Every holding also belongs to a CryptoPortfolio (below) — a user-defined
group like "long-term" or "memes" — so the same coin can be tracked
separately in more than one portfolio (each as its own CryptoHolding row,
since coingecko_id is deliberately not unique).
"""
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.asset import Asset
from app.models.enums import CryptoTransactionType
from app.models.mixins import TimestampMixin


class CryptoPortfolio(Base, TimestampMixin):
    """A user-defined grouping of crypto holdings (e.g. "long-term",
    "real estate fund", "memes") — same shape as Account (id, name, color,
    is_archived), but scoped to the Crypto tab instead of Transactions.
    Every CryptoHolding belongs to exactly one portfolio (see
    CryptoHolding.portfolio_id below); there's no "ungrouped" state."""

    __tablename__ = "crypto_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Hex color for the portfolio's tab dot — auto-assigned from the app's
    # categorical palette at creation time (see services/crypto_service.py's
    # _next_portfolio_color), not user-editable, same as Account.color.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    holdings: Mapped[list["CryptoHolding"]] = relationship(back_populates="portfolio")


class CryptoHolding(Base, TimestampMixin):
    """1:1 extension of an Asset (asset_class=CRYPTO) — asset_id doubles as
    this table's own primary key rather than a separate id+unique
    constraint, so the relationship can never drift into a 1:many by
    accident. Deleting the Asset (the existing DELETE /assets/{id}) cascades
    here too, and cascades again to every CryptoTransaction — there's no
    separate "delete the whole holding" endpoint."""

    __tablename__ = "crypto_holdings"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    # Which portfolio this coin is tracked under (see CryptoPortfolio above).
    # RESTRICT, not CASCADE: deleting a non-empty portfolio is blocked at the
    # service layer (services/crypto_service.py's delete_portfolio) rather
    # than silently taking its holdings down with it.
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("crypto_portfolios.id", ondelete="RESTRICT"), nullable=False
    )

    # CoinGecko's stable coin id (e.g. "bitcoin") — NOT the ticker symbol,
    # which collides across unrelated coins (CoinGecko lists dozens of
    # differently-named coins that all use e.g. "SOL"-like tickers).
    coingecko_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Denormalized from CoinGecko at add-time so the holdings list can
    # render a ticker/name/logo without an extra lookup per row.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    thumb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Free-form, user-entered — which chain this specific holding actually
    # sits on (e.g. "Ethereum", "Tron", "Arbitrum"). Deliberately not an
    # enum: CoinGecko doesn't expose per-holding chain data (the same
    # coingecko_id like "tether" covers the token across every chain it's
    # issued on), and new chains appear too often for a fixed list to keep
    # up. Lets a stablecoin held across several networks be told apart by
    # counterparty/bridge risk, which risk_level alone can't capture.
    network: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Cached from the last successful sync (services/crypto_service.py) —
    # in the app's display currency (see AppSettings.currency). Null until
    # the first sync completes.
    last_price: Mapped[Numeric | None] = mapped_column(Numeric(38, 18), nullable=True)
    price_change_1h: Mapped[Numeric | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_change_24h: Mapped[Numeric | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_change_7d: Mapped[Numeric | None] = mapped_column(Numeric(10, 4), nullable=True)
    # 30d and 1y ride along on the same batched CoinGecko call as the three
    # above — no extra API cost. 1y stands in for "all time" on the Crypto
    # tab's Best/Worst Performer stat (see routes/crypto.py): CoinGecko's
    # free tier caps historical lookback at 365 days regardless, so 1y is
    # already the most "all time" this API key can ever give us.
    price_change_30d: Mapped[Numeric | None] = mapped_column(Numeric(10, 4), nullable=True)
    price_change_1y: Mapped[Numeric | None] = mapped_column(Numeric(10, 4), nullable=True)

    asset: Mapped["Asset"] = relationship()
    portfolio: Mapped["CryptoPortfolio"] = relationship(back_populates="holdings")
    transactions: Mapped[list["CryptoTransaction"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan", order_by="CryptoTransaction.date"
    )


class CryptoTransaction(Base, TimestampMixin):
    """One buy or sell against a holding. Quantity held and average buy
    price are both derived by replaying this log in date order — see
    services/crypto_service.py's _compute_position for why a sell can't
    just be "negative quantity" the way it can for a Goal contribution: it
    must leave the remaining coins' average cost basis alone."""

    __tablename__ = "crypto_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("crypto_holdings.asset_id", ondelete="CASCADE"), nullable=False)
    type: Mapped[CryptoTransactionType] = mapped_column(
        Enum(CryptoTransactionType, name="crypto_transaction_type", native_enum=False, length=10), nullable=False
    )
    quantity: Mapped[Numeric] = mapped_column(Numeric(38, 18), nullable=False)
    # Price paid (buy) or received (sell) per unit, in the app's display
    # currency at the time of the transaction — not re-derived later, since
    # what you actually paid doesn't change with today's market price.
    price_per_unit: Mapped[Numeric] = mapped_column(Numeric(38, 18), nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    holding: Mapped["CryptoHolding"] = relationship(back_populates="transactions")


class CryptoSyncState(Base):
    """Singleton row (id=1, same get-or-create pattern as AppSettings) — the
    single global timestamp of the last successful CoinGecko price refresh.
    One timestamp for every holding, not one per holding: a refresh always
    re-prices every tracked coin in a single batched request (see
    services/crypto_service.py), so there's only ever one "last synced"
    moment to track."""

    __tablename__ = "crypto_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
