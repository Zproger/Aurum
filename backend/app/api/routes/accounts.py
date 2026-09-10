from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import log_destructive
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.account_service import create_account, delete_account, list_accounts, update_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountWithBalance])
async def read_accounts(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[AccountWithBalance]:
    return await list_accounts(session, include_archived)


@router.post("", response_model=AccountWithBalance, status_code=201)
async def create_account_route(
    payload: AccountCreate, session: AsyncSession = Depends(get_session)
) -> AccountWithBalance:
    return await create_account(session, payload)


@router.patch("/{account_id}", response_model=AccountWithBalance)
async def update_account_route(
    account_id: int, payload: AccountUpdate, session: AsyncSession = Depends(get_session)
) -> AccountWithBalance:
    return await update_account(session, account_id, payload)


@router.delete("/{account_id}", status_code=204)
async def delete_account_route(account_id: int, session: AsyncSession = Depends(get_session)) -> None:
    # Takes every transaction on the account with it, so it's worth a line in
    # the log even though the UI asks for confirmation first.
    await delete_account(session, account_id)
    log_destructive("account.deleted", account_id=account_id)
