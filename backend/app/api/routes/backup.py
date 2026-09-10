from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import log_destructive
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/export", response_model=BackupPayload)
async def export_backup(session: AsyncSession = Depends(get_session)) -> BackupPayload:
    return await build_backup(session)


@router.post("/import")
async def import_backup(payload: BackupPayload, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    # Logged before the fact as well as after: if the restore dies partway
    # (it rolls back, but the process could also be killed outright), the
    # "started" line is the only evidence it was ever attempted.
    log_destructive(
        "backup.restore.started",
        exported_at=payload.exported_at,
        source_app_version=payload.app_version,
        accounts=len(payload.accounts),
        transactions=len(payload.transactions),
    )
    await restore_backup(session, payload)
    log_destructive("backup.restore.completed", transactions=len(payload.transactions))
    return {"status": "ok"}
