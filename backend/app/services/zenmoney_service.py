"""ZenMoney synchronization service.

Fetches accounts, categories/tags, merchants, and transactions from ZenMoney's
v8 diff API (https://api.zenmoney.ru/v8/diff/) and upserts them into Aurum's
PostgreSQL schema using serverTimestamp diff tracking.
"""
from datetime import date as date_, datetime, timezone
from decimal import Decimal
import time

from fastapi import HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.text import capitalize_first_letter
from app.models.account import Account
from app.models.category import Category
from app.models.enums import AccountType, CategoryKind, TransactionType
from app.models.transaction import Transaction
from app.models.zenmoney import ZenmoneySyncState
from app.schemas.zenmoney import ZenmoneyStatusRead, ZenmoneySyncResult

ZENMONEY_DIFF_URL = "https://api.zenmoney.ru/v8/diff/"

# Default categorical color palette for categories synced without a custom color.
_COLOR_PALETTE = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#84cc16",  # lime
    "#f97316",  # orange
    "#64748b",  # slate
]

# Fallback map for common ZenMoney instrument IDs to ISO currency codes.
_KNOWN_INSTRUMENTS = {
    1: "USD",
    2: "RUB",
    3: "EUR",
    4: "UAH",
    5467: "GBP",
    5534: "KZT",
    5535: "BYN",
    5536: "GEL",
    5537: "AMD",
    5538: "TRY",
}

_ACCOUNT_TYPE_MAP = {
    "checking": AccountType.CHECKING,
    "cash": AccountType.CASH,
    "ccard": AccountType.CREDIT_CARD,
    "deposit": AccountType.SAVINGS,
    "loan": AccountType.OTHER,
    "investment": AccountType.INVESTMENT,
    "other": AccountType.OTHER,
}


def _require_token() -> str:
    token = get_settings().zenmoney_token.strip()
    if not token:
        raise HTTPException(
            status_code=400,
            detail=(
                "ZenMoney token not configured — set AURUM_ZENMONEY_TOKEN in .env "
                "(get your token from your ZenMoney developer profile / settings)."
            ),
        )
    return token


async def get_or_create_sync_state(session: AsyncSession) -> ZenmoneySyncState:
    state = await session.get(ZenmoneySyncState, 1)
    if state is None:
        state = ZenmoneySyncState(
            id=1,
            server_timestamp=0,
            last_synced_at=None,
            synced_accounts_count=0,
            synced_categories_count=0,
            synced_transactions_count=0,
            last_error=None,
        )
        session.add(state)
        await session.flush()
    return state


async def get_zenmoney_status(session: AsyncSession) -> ZenmoneyStatusRead:
    token = get_settings().zenmoney_token.strip()
    state = await get_or_create_sync_state(session)
    return ZenmoneyStatusRead(
        is_configured=bool(token),
        server_timestamp=state.server_timestamp,
        last_synced_at=state.last_synced_at,
        synced_accounts_count=state.synced_accounts_count,
        synced_categories_count=state.synced_categories_count,
        synced_transactions_count=state.synced_transactions_count,
        last_error=state.last_error,
    )


async def _fetch_diff(token: str, server_ts: int) -> dict:
    payload = {
        "serverTimestamp": server_ts,
        "currentClientTimestamp": int(time.time()),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Aurum-ZenMoney-Sync/1.0",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(ZENMONEY_DIFF_URL, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            msg = f"ZenMoney API returned HTTP {exc.response.status_code}: {exc.response.text}"
            raise HTTPException(status_code=400, detail=msg) from exc
        except httpx.RequestError as exc:
            msg = f"Failed to connect to ZenMoney API: {exc}"
            raise HTTPException(status_code=502, detail=msg) from exc


def _parse_instruments(instruments_raw: list[dict]) -> dict[int, str]:
    mapping = dict(_KNOWN_INSTRUMENTS)
    for inst in instruments_raw:
        inst_id = inst.get("id")
        short_title = inst.get("shortTitle")
        if inst_id and short_title:
            mapping[inst_id] = str(short_title).upper()
    return mapping


async def _sync_accounts(
    session: AsyncSession,
    accounts_raw: list[dict],
    instruments: dict[int, str],
) -> dict[str, int]:
    """Upserts ZenMoney accounts into Aurum Account table and returns {zm_uuid: aurum_id}."""
    # Load all existing accounts into memory
    existing_accounts = (await session.execute(select(Account))).scalars().all()
    account_map: dict[str, int] = {}
    accounts_by_zm_id: dict[str, Account] = {}

    for acc in existing_accounts:
        if acc.zenmoney_id:
            account_map[acc.zenmoney_id] = acc.id
            accounts_by_zm_id[acc.zenmoney_id] = acc

    for acc_raw in accounts_raw:
        zm_id = acc_raw.get("id")
        if not zm_id:
            continue

        raw_title = acc_raw.get("title") or "Счёт ZenMoney"
        title = capitalize_first_letter(raw_title.strip()[:100])
        acc_type_str = acc_raw.get("type", "checking")
        acc_type = _ACCOUNT_TYPE_MAP.get(acc_type_str, AccountType.CHECKING)
        instrument_id = acc_raw.get("instrument", 2)
        currency = instruments.get(instrument_id, "RUB")
        is_archived = bool(acc_raw.get("archive", False))

        existing = accounts_by_zm_id.get(zm_id)
        if existing:
            existing.name = title
            existing.type = acc_type
            existing.currency = currency
            existing.is_archived = is_archived
        else:
            new_acc = Account(
                name=title,
                type=acc_type,
                currency=currency,
                is_archived=is_archived,
                zenmoney_id=zm_id,
            )
            session.add(new_acc)
            await session.flush()
            account_map[zm_id] = new_acc.id
            accounts_by_zm_id[zm_id] = new_acc

    return account_map


async def _sync_categories(
    session: AsyncSession,
    tags_raw: list[dict],
) -> dict[str, int]:
    """Upserts ZenMoney tags as Categories in Aurum and returns {zm_tag_uuid: aurum_cat_id}."""
    existing_cats = (await session.execute(select(Category))).scalars().all()
    category_map: dict[str, int] = {}
    cats_by_zm_id: dict[str, Category] = {}

    for cat in existing_cats:
        if cat.zenmoney_id:
            category_map[cat.zenmoney_id] = cat.id
            cats_by_zm_id[cat.zenmoney_id] = cat

    # Pass 1: Upsert all categories
    for idx, tag_raw in enumerate(tags_raw):
        zm_id = tag_raw.get("id")
        if not zm_id or tag_raw.get("deleted"):
            continue

        title_raw = tag_raw.get("title") or "Категория"
        title = capitalize_first_letter(title_raw.strip()[:100])

        show_income = bool(tag_raw.get("showIncome", False))
        show_outcome = bool(tag_raw.get("showOutcome", True))
        kind = CategoryKind.INCOME if (show_income and not show_outcome) else CategoryKind.EXPENSE

        color = _COLOR_PALETTE[idx % len(_COLOR_PALETTE)]

        existing = cats_by_zm_id.get(zm_id)
        if existing:
            existing.name = title
            existing.kind = kind
        else:
            new_cat = Category(
                name=title,
                kind=kind,
                color=color,
                sort_order=idx,
                is_default=False,
                zenmoney_id=zm_id,
            )
            session.add(new_cat)
            await session.flush()
            category_map[zm_id] = new_cat.id
            cats_by_zm_id[zm_id] = new_cat

    # Pass 2: Set parent_id for hierarchical categories
    for tag_raw in tags_raw:
        zm_id = tag_raw.get("id")
        if not zm_id or tag_raw.get("deleted"):
            continue
        parent_zm_id = tag_raw.get("parent")
        if parent_zm_id and parent_zm_id in category_map:
            cat = cats_by_zm_id.get(zm_id)
            if cat:
                cat.parent_id = category_map[parent_zm_id]

    return category_map


def _parse_tx_date(date_str: str | None) -> date_:
    if not date_str:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return datetime.now(timezone.utc).date()


async def _sync_transactions(
    session: AsyncSession,
    transactions_raw: list[dict],
    account_map: dict[str, int],
    category_map: dict[str, int],
    merchant_map: dict[str, str],
) -> tuple[int, int]:
    """Processes ZenMoney transactions: inserts, updates, and deletes.

    Returns (synced_count, deleted_count).
    """
    if not transactions_raw:
        return 0, 0

    all_categories = (await session.execute(select(Category))).scalars().all()
    categories_by_id = {c.id: c for c in all_categories}

    # Load existing synced transactions
    existing_txs = (await session.execute(select(Transaction).where(Transaction.zenmoney_id.isnot(None)))).scalars().all()
    txs_by_zm_id: dict[str, Transaction] = {t.zenmoney_id: t for t in existing_txs if t.zenmoney_id}

    synced_count = 0
    deleted_count = 0

    for tx_raw in transactions_raw:
        zm_id = tx_raw.get("id")
        if not zm_id:
            continue

        is_deleted = bool(tx_raw.get("deleted", False))
        if is_deleted:
            existing = txs_by_zm_id.get(zm_id)
            if existing:
                await session.delete(existing)
                txs_by_zm_id.pop(zm_id, None)
                deleted_count += 1
            continue

        try:
            income_val = Decimal(str(tx_raw.get("income", 0) or 0))
            outcome_val = Decimal(str(tx_raw.get("outcome", 0) or 0))
        except Exception:
            continue

        inc_acc_zm = tx_raw.get("incomeAccount")
        out_acc_zm = tx_raw.get("outcomeAccount")

        inc_acc_id = account_map.get(inc_acc_zm) if inc_acc_zm else None
        out_acc_id = account_map.get(out_acc_zm) if out_acc_zm else None

        # Ignore 0 amount transactions
        if income_val == 0 and outcome_val == 0:
            continue

        # Determine transaction type and corresponding accounts & amount
        if outcome_val > 0 and income_val == 0:
            tx_type = TransactionType.EXPENSE
            amount = outcome_val
            acc_id = out_acc_id or inc_acc_id
            transfer_acc_id = None
        elif income_val > 0 and outcome_val == 0:
            tx_type = TransactionType.INCOME
            amount = income_val
            acc_id = inc_acc_id or out_acc_id
            transfer_acc_id = None
        elif income_val > 0 and outcome_val > 0 and inc_acc_zm != out_acc_zm:
            tx_type = TransactionType.TRANSFER
            amount = outcome_val
            acc_id = out_acc_id
            transfer_acc_id = inc_acc_id
        elif income_val > 0 and outcome_val > 0 and inc_acc_zm == out_acc_zm:
            # Same account balance adjustment / correction
            if income_val >= outcome_val:
                tx_type = TransactionType.INCOME
                amount = income_val - outcome_val
            else:
                tx_type = TransactionType.EXPENSE
                amount = outcome_val - income_val
            acc_id = inc_acc_id or out_acc_id
            transfer_acc_id = None
        else:
            continue

        if acc_id is None:
            # Cannot store transaction without valid account
            continue

        # Resolve category (only for INCOME or EXPENSE, never for TRANSFER)
        category_id: int | None = None
        if tx_type != TransactionType.TRANSFER:
            tag_list = tx_raw.get("tag") or []
            if isinstance(tag_list, list):
                for tag_zm_id in tag_list:
                    if tag_zm_id in category_map:
                        cat_candidate_id = category_map[tag_zm_id]
                        cat_obj = categories_by_id.get(cat_candidate_id)
                        if cat_obj:
                            expected_kind = CategoryKind.INCOME if tx_type == TransactionType.INCOME else CategoryKind.EXPENSE
                            if cat_obj.kind == expected_kind:
                                category_id = cat_candidate_id
                                break

        # Merchant and Description
        merchant_name = merchant_map.get(tx_raw.get("merchant") or "")
        payee = tx_raw.get("payee") or tx_raw.get("originalPayee")
        comment = tx_raw.get("comment")

        final_merchant = merchant_name or payee
        if final_merchant:
            final_merchant = capitalize_first_letter(final_merchant.strip()[:150])

        cat_title = categories_by_id[category_id].name if (category_id and category_id in categories_by_id) else None
        raw_description = payee or comment or merchant_name or cat_title or ("Перевод" if tx_type == TransactionType.TRANSFER else "Транзакция")
        final_description = capitalize_first_letter(raw_description.strip()[:255])
        final_notes = comment.strip() if comment else None

        tx_date = _parse_tx_date(tx_raw.get("date"))

        existing = txs_by_zm_id.get(zm_id)
        if existing:
            existing.account_id = acc_id
            existing.transfer_account_id = transfer_acc_id
            existing.category_id = category_id
            existing.type = tx_type
            existing.amount = amount
            existing.description = final_description
            existing.merchant = final_merchant
            existing.notes = final_notes
            existing.date = tx_date
        else:
            new_tx = Transaction(
                account_id=acc_id,
                transfer_account_id=transfer_acc_id,
                category_id=category_id,
                type=tx_type,
                amount=amount,
                description=final_description,
                merchant=final_merchant,
                notes=final_notes,
                date=tx_date,
                zenmoney_id=zm_id,
            )
            session.add(new_tx)
            txs_by_zm_id[zm_id] = new_tx

        synced_count += 1

    return synced_count, deleted_count


async def sync_zenmoney(
    session: AsyncSession,
    force_full: bool = False,
) -> ZenmoneySyncResult:
    """Executes ZenMoney synchronization against diff API."""
    token = _require_token()
    state = await get_or_create_sync_state(session)

    server_ts = 0 if force_full else state.server_timestamp

    try:
        data = await _fetch_diff(token, server_ts)
    except Exception as exc:
        state.last_error = str(exc)
        await session.commit()
        raise

    new_server_ts = data.get("serverTimestamp") or server_ts
    instruments = _parse_instruments(data.get("instrument") or [])

    # Merchants lookup map: {zm_id: title}
    merchant_map: dict[str, str] = {}
    for m in data.get("merchant") or []:
        m_id = m.get("id")
        m_title = m.get("title")
        if m_id and m_title:
            merchant_map[m_id] = m_title.strip()

    # 1. Accounts
    account_map = await _sync_accounts(session, data.get("account") or [], instruments)

    # 2. Categories
    category_map = await _sync_categories(session, data.get("tag") or [])

    # 3. Transactions
    synced_tx_count, deleted_tx_count = await _sync_transactions(
        session,
        data.get("transaction") or [],
        account_map,
        category_map,
        merchant_map,
    )

    # Update Sync State
    total_synced_accounts = len(account_map)
    total_synced_categories = len(category_map)
    # Count total active synced transactions in DB
    total_synced_txs = (
        await session.execute(select(Transaction).where(Transaction.zenmoney_id.isnot(None)))
    ).scalars().all()

    now_utc = datetime.now(timezone.utc)
    state.server_timestamp = new_server_ts
    state.last_synced_at = now_utc
    state.synced_accounts_count = total_synced_accounts
    state.synced_categories_count = total_synced_categories
    state.synced_transactions_count = len(total_synced_txs)
    state.last_error = None

    await session.commit()

    return ZenmoneySyncResult(
        success=True,
        message="ZenMoney synchronization completed successfully.",
        server_timestamp=new_server_ts,
        accounts_synced=total_synced_accounts,
        categories_synced=total_synced_categories,
        transactions_synced=synced_tx_count,
        transactions_deleted=deleted_tx_count,
        last_synced_at=now_utc,
    )
