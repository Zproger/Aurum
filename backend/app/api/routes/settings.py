from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.settings import AppSettings
from app.schemas.settings import AppSettingsRead, AppSettingsUpdate
from app.services.settings_service import get_or_create_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


# Both routes still return the ORM row as-is: AppSettingsRead.app_version
# isn't a stored column, it defaults to APP_VERSION when FastAPI validates
# the response (see schemas/settings.py).
@router.get("", response_model=AppSettingsRead)
async def read_settings(session: AsyncSession = Depends(get_session)) -> AppSettings:
    return await get_or_create_app_settings(session)


@router.patch("", response_model=AppSettingsRead)
async def update_settings(payload: AppSettingsUpdate, session: AsyncSession = Depends(get_session)) -> AppSettings:
    settings = await get_or_create_app_settings(session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await session.commit()
    await session.refresh(settings)
    return settings
