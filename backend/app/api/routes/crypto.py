from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.crypto import (
    CryptoHistoryResponse,
    CryptoHoldingCreate,
    CryptoHoldingRead,
    CryptoHoldingUpdate,
    CryptoPerformanceResponse,
    CryptoPortfolioCreate,
    CryptoPortfolioRead,
    CryptoPortfolioUpdate,
    CryptoSearchResult,
    CryptoSyncResult,
    CryptoTransactionCreate,
    CryptoTransactionRead,
    CryptoTransactionUpdate,
)
from app.services.crypto_service import (
    CRYPTO_RANGE_DAYS,
    add_transaction,
    create_holding,
    create_portfolio,
    delete_portfolio,
    delete_transaction,
    get_90d_performance,
    get_crypto_history,
    list_portfolios,
    list_transactions,
    refresh_prices,
    search_coins,
    update_holding,
    update_portfolio,
    update_transaction,
)

router = APIRouter(prefix="/crypto", tags=["crypto"])


@router.get("/portfolios", response_model=list[CryptoPortfolioRead])
async def read_portfolios(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[CryptoPortfolioRead]:
    return await list_portfolios(session, include_archived)


@router.post("/portfolios", response_model=CryptoPortfolioRead, status_code=201)
async def create_portfolio_route(
    payload: CryptoPortfolioCreate, session: AsyncSession = Depends(get_session)
) -> CryptoPortfolioRead:
    return await create_portfolio(session, payload)


@router.patch("/portfolios/{portfolio_id}", response_model=CryptoPortfolioRead)
async def update_portfolio_route(
    portfolio_id: int, payload: CryptoPortfolioUpdate, session: AsyncSession = Depends(get_session)
) -> CryptoPortfolioRead:
    return await update_portfolio(session, portfolio_id, payload)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def delete_portfolio_route(portfolio_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_portfolio(session, portfolio_id)


@router.get("/holdings", response_model=CryptoSyncResult)
async def read_holdings(
    portfolio_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> CryptoSyncResult:
    """Opening the Crypto tab lands here — this is also where the lazy
    once-a-day auto-refresh happens (see services/crypto_service.py):
    prices only actually get re-fetched from CoinGecko if 24h have passed
    since the last sync, otherwise this just reads the current cache."""
    return await refresh_prices(session, force=False, portfolio_id=portfolio_id)


@router.post("/refresh", response_model=CryptoSyncResult)
async def refresh_holdings(
    portfolio_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> CryptoSyncResult:
    """The "Refresh prices" button — always hits CoinGecko regardless of
    the once-a-day window."""
    return await refresh_prices(session, force=True, portfolio_id=portfolio_id)


@router.post("/holdings", response_model=CryptoHoldingRead, status_code=201)
async def create_holding_route(
    payload: CryptoHoldingCreate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    return await create_holding(session, payload)


@router.patch("/holdings/{asset_id}", response_model=CryptoHoldingRead)
async def update_holding_route(
    asset_id: int, payload: CryptoHoldingUpdate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    """Updates holding-only metadata (currently just `network`) — quantity/
    price/date go through the /transactions routes below instead."""
    return await update_holding(session, asset_id, payload)


@router.post("/holdings/{asset_id}/transactions", response_model=CryptoHoldingRead, status_code=201)
async def add_transaction_route(
    asset_id: int, payload: CryptoTransactionCreate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    """Buy more of, or sell some of, a coin already being tracked."""
    return await add_transaction(session, asset_id, payload)


@router.get("/holdings/{asset_id}/transactions", response_model=list[CryptoTransactionRead])
async def list_transactions_route(
    asset_id: int, session: AsyncSession = Depends(get_session)
) -> list[CryptoTransactionRead]:
    return await list_transactions(session, asset_id)


@router.patch("/transactions/{transaction_id}", response_model=CryptoHoldingRead)
async def update_transaction_route(
    transaction_id: int, payload: CryptoTransactionUpdate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    return await update_transaction(session, transaction_id, payload)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction_route(transaction_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_transaction(session, transaction_id)


@router.get("/search", response_model=list[CryptoSearchResult])
async def search_coins_route(q: str = Query(min_length=1, max_length=100)) -> list[CryptoSearchResult]:
    return await search_coins(q)


_HISTORY_RANGES = sorted(set(CRYPTO_RANGE_DAYS) | {"all"})
_HISTORY_RANGE_PATTERN = f"^({'|'.join(_HISTORY_RANGES)})$"


@router.get("/history", response_model=CryptoHistoryResponse)
async def read_crypto_history(
    range: str = Query(default="30d", pattern=_HISTORY_RANGE_PATTERN),
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> CryptoHistoryResponse:
    return await get_crypto_history(session, range, portfolio_id)


@router.get("/performance/90d", response_model=CryptoPerformanceResponse)
async def read_90d_performance(
    portfolio_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> CryptoPerformanceResponse:
    """Backs the Best/Worst Performer stat only while the 90d range is
    selected — see get_90d_performance's docstring for why this is a
    separate on-demand call instead of a cached field like 7d/30d/1y."""
    return await get_90d_performance(session, portfolio_id)
