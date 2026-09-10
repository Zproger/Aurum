"""Full-database JSON backup & restore.

Exports every row (accounts, categories, transactions, assets, asset
valuations) as one portable JSON document a user can download from the
browser and re-upload later. Restore fully REPLACES existing data — it's a
snapshot restore, not a merge — so the whole operation runs in one DB
transaction: a corrupt or incompatible file is rejected (referential checks
run first, before any row is touched), and any failure during the swap rolls
the database back to exactly where it was, so a bad file never leaves the
app half-restored.
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import APP_VERSION
from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.budget import Budget
from app.models.category import Category
from app.models.crypto import CryptoHolding, CryptoPortfolio, CryptoTransaction
from app.models.goal import Goal, GoalContribution
from app.models.recurring import RecurringTransaction
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.backup import (
    AccountBackup,
    AppSettingsBackup,
    AssetBackup,
    AssetValuationBackup,
    BackupPayload,
    BudgetBackup,
    CategoryBackup,
    CryptoHoldingBackup,
    CryptoPortfolioBackup,
    CryptoTransactionBackup,
    GoalBackup,
    GoalContributionBackup,
    RecurringTransactionBackup,
    TagBackup,
    TransactionBackup,
    TransactionSplitBackup,
)

logger = logging.getLogger(__name__)

BACKUP_FORMAT_VERSION = 1


async def build_backup(session: AsyncSession) -> BackupPayload:
    accounts = (await session.execute(select(Account))).scalars().all()
    categories = (await session.execute(select(Category))).scalars().all()
    tags = (await session.execute(select(Tag))).scalars().all()
    transactions = (await session.execute(select(Transaction).options(selectinload(Transaction.tags)))).scalars().all()
    transaction_splits = (await session.execute(select(TransactionSplit))).scalars().all()
    assets = (await session.execute(select(Asset))).scalars().all()
    valuations = (await session.execute(select(AssetValuation))).scalars().all()
    crypto_portfolios = (await session.execute(select(CryptoPortfolio))).scalars().all()
    crypto_holdings = (await session.execute(select(CryptoHolding))).scalars().all()
    crypto_transactions = (await session.execute(select(CryptoTransaction))).scalars().all()
    budgets = (await session.execute(select(Budget))).scalars().all()
    goals = (await session.execute(select(Goal))).scalars().all()
    goal_contributions = (await session.execute(select(GoalContribution))).scalars().all()
    recurring_transactions = (await session.execute(select(RecurringTransaction))).scalars().all()
    app_settings = await session.get(AppSettings, 1)

    return BackupPayload(
        aurum_backup_version=BACKUP_FORMAT_VERSION,
        exported_at=datetime.now(timezone.utc),
        app_version=APP_VERSION,
        accounts=[AccountBackup.model_validate(row) for row in accounts],
        categories=[CategoryBackup.model_validate(row) for row in categories],
        tags=[TagBackup.model_validate(row) for row in tags],
        transactions=[
            TransactionBackup.model_validate(row, from_attributes=True).model_copy(
                update={"tag_ids": [tag.id for tag in row.tags]}
            )
            for row in transactions
        ],
        transaction_splits=[TransactionSplitBackup.model_validate(row) for row in transaction_splits],
        assets=[AssetBackup.model_validate(row) for row in assets],
        asset_valuations=[AssetValuationBackup.model_validate(row) for row in valuations],
        crypto_portfolios=[CryptoPortfolioBackup.model_validate(row) for row in crypto_portfolios],
        crypto_holdings=[CryptoHoldingBackup.model_validate(row) for row in crypto_holdings],
        crypto_transactions=[CryptoTransactionBackup.model_validate(row) for row in crypto_transactions],
        budgets=[BudgetBackup.model_validate(row) for row in budgets],
        goals=[GoalBackup.model_validate(row) for row in goals],
        goal_contributions=[GoalContributionBackup.model_validate(row) for row in goal_contributions],
        recurring_transactions=[RecurringTransactionBackup.model_validate(row) for row in recurring_transactions],
        app_settings=AppSettingsBackup.model_validate(app_settings) if app_settings else AppSettingsBackup(currency="USD"),
    )


def _validate_references(payload: BackupPayload) -> None:
    account_ids = {row.id for row in payload.accounts}
    category_ids = {row.id for row in payload.categories}
    asset_ids = {row.id for row in payload.assets}
    tag_ids = {row.id for row in payload.tags}

    for c in payload.categories:
        if c.parent_id is not None and c.parent_id not in category_ids:
            raise HTTPException(400, f"Category {c.id} references unknown parent_id {c.parent_id}")

    for t in payload.transactions:
        if t.account_id not in account_ids:
            raise HTTPException(400, f"Transaction {t.id} references unknown account_id {t.account_id}")
        if t.transfer_account_id is not None and t.transfer_account_id not in account_ids:
            raise HTTPException(
                400, f"Transaction {t.id} references unknown transfer_account_id {t.transfer_account_id}"
            )
        if t.category_id is not None and t.category_id not in category_ids:
            raise HTTPException(400, f"Transaction {t.id} references unknown category_id {t.category_id}")
        for tag_id in t.tag_ids:
            if tag_id not in tag_ids:
                raise HTTPException(400, f"Transaction {t.id} references unknown tag_id {tag_id}")

    transaction_ids = {row.id for row in payload.transactions}
    for s in payload.transaction_splits:
        if s.transaction_id not in transaction_ids:
            raise HTTPException(400, f"Transaction split {s.id} references unknown transaction_id {s.transaction_id}")
        if s.category_id is not None and s.category_id not in category_ids:
            raise HTTPException(400, f"Transaction split {s.id} references unknown category_id {s.category_id}")

    for v in payload.asset_valuations:
        if v.asset_id not in asset_ids:
            raise HTTPException(400, f"Asset valuation {v.id} references unknown asset_id {v.asset_id}")

    crypto_portfolio_ids = {p.id for p in payload.crypto_portfolios}
    crypto_holding_asset_ids = {h.asset_id for h in payload.crypto_holdings}
    for h in payload.crypto_holdings:
        if h.asset_id not in asset_ids:
            raise HTTPException(400, f"Crypto holding {h.asset_id} references unknown asset_id {h.asset_id}")
        # portfolio_id is allowed to be None (a pre-portfolios backup) — that
        # case is resolved to an auto-created fallback portfolio at restore
        # time, not validated here.
        if h.portfolio_id is not None and h.portfolio_id not in crypto_portfolio_ids:
            raise HTTPException(
                400, f"Crypto holding {h.asset_id} references unknown portfolio_id {h.portfolio_id}"
            )

    for tx in payload.crypto_transactions:
        if tx.asset_id not in crypto_holding_asset_ids:
            raise HTTPException(400, f"Crypto transaction {tx.id} references unknown asset_id {tx.asset_id}")

    for b in payload.budgets:
        if b.category_id not in category_ids:
            raise HTTPException(400, f"Budget {b.id} references unknown category_id {b.category_id}")

    goal_ids = {row.id for row in payload.goals}
    for c in payload.goal_contributions:
        if c.goal_id not in goal_ids:
            raise HTTPException(400, f"Goal contribution {c.id} references unknown goal_id {c.goal_id}")

    for r in payload.recurring_transactions:
        if r.account_id not in account_ids:
            raise HTTPException(400, f"Recurring transaction {r.id} references unknown account_id {r.account_id}")
        if r.transfer_account_id is not None and r.transfer_account_id not in account_ids:
            raise HTTPException(
                400,
                f"Recurring transaction {r.id} references unknown transfer_account_id {r.transfer_account_id}",
            )
        if r.category_id is not None and r.category_id not in category_ids:
            raise HTTPException(400, f"Recurring transaction {r.id} references unknown category_id {r.category_id}")


async def _reset_sequence(session: AsyncSession, table: str, rows: list) -> None:
    """Bulk-inserting rows with explicit ids doesn't advance the table's
    identity sequence, so the next auto-generated id would collide — bump it
    to max(id) after a restore. `table` is always one of our five hardcoded
    table names, never user input."""
    if not rows:
        return
    max_id = max(row.id for row in rows)
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), :max_id)"), {"max_id": max_id}
    )


async def restore_backup(session: AsyncSession, payload: BackupPayload) -> None:
    if payload.aurum_backup_version != BACKUP_FORMAT_VERSION:
        raise HTTPException(
            400,
            f"Unsupported backup version {payload.aurum_backup_version} "
            f"(this Aurum version supports {BACKUP_FORMAT_VERSION})",
        )

    _validate_references(payload)

    try:
        # Children before parents.
        await session.execute(delete(AssetValuation))
        await session.execute(delete(CryptoTransaction))
        await session.execute(delete(CryptoHolding))
        await session.execute(delete(CryptoPortfolio))
        await session.execute(delete(Budget))
        await session.execute(delete(GoalContribution))
        await session.execute(delete(Goal))
        await session.execute(delete(RecurringTransaction))
        # Deleting transactions cascades transaction_tags and
        # transaction_splits rows (ON DELETE CASCADE) — deleted explicitly
        # here anyway to keep this block's ordering self-documenting.
        await session.execute(delete(TransactionSplit))
        await session.execute(delete(Transaction))
        await session.execute(delete(Tag))
        await session.execute(delete(Asset))
        await session.execute(delete(Category))
        await session.execute(delete(Account))

        # Parents before children. Categories are additionally self-referential
        # (parent_id points at another row in the same table) — sort
        # top-level categories first so a subcategory's FK is never inserted
        # ahead of the row it points to.
        categories_in_order = sorted(payload.categories, key=lambda row: row.parent_id is not None)

        session.add_all(Account(**row.model_dump()) for row in payload.accounts)
        session.add_all(Category(**row.model_dump()) for row in categories_in_order)
        session.add_all(Asset(**row.model_dump()) for row in payload.assets)

        # Tags and transactions are kept in id-keyed dicts (rather than a
        # plain add_all) — transaction.tags is a relationship, not a column
        # in model_dump(), so it has to be wired up from live ORM objects
        # once everything is flushed and has real identities.
        tags_by_id = {row.id: Tag(**row.model_dump()) for row in payload.tags}
        session.add_all(tags_by_id.values())
        # tags=[] at construction keeps the collection "loaded" on the
        # transient object — reassigning it after flush (below) would
        # otherwise trigger an implicit lazy-load, which async SQLAlchemy
        # can't do outside an explicit await (MissingGreenlet).
        transactions_by_id = {
            row.id: Transaction(**row.model_dump(exclude={"tag_ids"}), tags=[]) for row in payload.transactions
        }
        session.add_all(transactions_by_id.values())
        session.add_all(TransactionSplit(**row.model_dump()) for row in payload.transaction_splits)

        session.add_all(AssetValuation(**row.model_dump()) for row in payload.asset_valuations)

        session.add_all(CryptoPortfolio(**row.model_dump()) for row in payload.crypto_portfolios)
        # A pre-portfolios backup has no crypto_portfolios and every holding's
        # portfolio_id is None — give those holdings a freshly created
        # fallback portfolio instead of leaving the NOT NULL column unset.
        # Wired up via the `portfolio` relationship (not a raw portfolio_id
        # int) because the fallback row has no id yet — same "assign the
        # relationship, not the id column, before flush" reasoning as
        # transactions_by_id/tags_by_id above.
        fallback_portfolio: CryptoPortfolio | None = None
        if any(row.portfolio_id is None for row in payload.crypto_holdings):
            fallback_portfolio = CryptoPortfolio(name="Main Portfolio", color="#2a78d6")
            session.add(fallback_portfolio)

        crypto_holdings = []
        for row in payload.crypto_holdings:
            holding = CryptoHolding(**row.model_dump(exclude={"portfolio_id"}))
            if row.portfolio_id is not None:
                holding.portfolio_id = row.portfolio_id
            else:
                holding.portfolio = fallback_portfolio
            crypto_holdings.append(holding)
        session.add_all(crypto_holdings)

        session.add_all(CryptoTransaction(**row.model_dump()) for row in payload.crypto_transactions)
        session.add_all(Budget(**row.model_dump()) for row in payload.budgets)
        session.add_all(Goal(**row.model_dump()) for row in payload.goals)
        session.add_all(GoalContribution(**row.model_dump()) for row in payload.goal_contributions)
        session.add_all(RecurringTransaction(**row.model_dump()) for row in payload.recurring_transactions)
        await session.flush()

        for row in payload.transactions:
            if row.tag_ids:
                transactions_by_id[row.id].tags = [tags_by_id[tag_id] for tag_id in row.tag_ids]
        if any(row.tag_ids for row in payload.transactions):
            await session.flush()

        await _reset_sequence(session, "accounts", payload.accounts)
        await _reset_sequence(session, "categories", payload.categories)
        await _reset_sequence(session, "tags", payload.tags)
        await _reset_sequence(session, "assets", payload.assets)
        await _reset_sequence(session, "transactions", payload.transactions)
        await _reset_sequence(session, "transaction_splits", payload.transaction_splits)
        await _reset_sequence(session, "asset_valuations", payload.asset_valuations)
        # Only needed for explicit-id portfolios from payload — a fallback
        # portfolio (no payload row) already got its id from the sequence
        # itself, so the sequence is already correctly positioned for it.
        await _reset_sequence(session, "crypto_portfolios", payload.crypto_portfolios)
        await _reset_sequence(session, "crypto_transactions", payload.crypto_transactions)
        await _reset_sequence(session, "budgets", payload.budgets)
        await _reset_sequence(session, "goals", payload.goals)
        await _reset_sequence(session, "goal_contributions", payload.goal_contributions)
        await _reset_sequence(session, "recurring_transactions", payload.recurring_transactions)

        # Singleton row — updated in place, not deleted/recreated (no
        # sequence to reset, id is always 1).
        app_settings = await session.get(AppSettings, 1)
        if app_settings is None:
            session.add(AppSettings(id=1, **payload.app_settings.model_dump()))
        else:
            for field, value in payload.app_settings.model_dump().items():
                setattr(app_settings, field, value)

        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        # The exception text is SQLAlchemy's, naming tables, columns and
        # constraints — a free map of the schema for anyone probing the API.
        # It goes to the container log, where the operator can actually read
        # it; the client gets told only that nothing changed.
        logger.exception("Backup restore failed")
        raise HTTPException(400, "Restore failed, no changes were made") from exc
