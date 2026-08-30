"""API routes for ZenMoney synchronization."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.zenmoney import (
    ZenmoneyStatusRead,
    ZenmoneySyncRequest,
    ZenmoneySyncResult,
)
from app.services.zenmoney_service import (
    get_zenmoney_status,
    sync_zenmoney,
)

router = APIRouter(prefix="/zenmoney", tags=["zenmoney"])


@router.get("/status", response_model=ZenmoneyStatusRead)
async def read_zenmoney_status(
    session: AsyncSession = Depends(get_session),
) -> ZenmoneyStatusRead:
    """Returns the current ZenMoney sync status, timestamps, and error state."""
    return await get_zenmoney_status(session)


@router.post("/sync", response_model=ZenmoneySyncResult)
async def trigger_zenmoney_sync(
    payload: ZenmoneySyncRequest = ZenmoneySyncRequest(),
    session: AsyncSession = Depends(get_session),
) -> ZenmoneySyncResult:
    """Triggers an on-demand synchronization with ZenMoney diff API."""
    return await sync_zenmoney(session, force_full=payload.force_full)
