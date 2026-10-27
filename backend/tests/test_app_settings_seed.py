"""Regression coverage for the fixed USD reporting currency.

Earlier releases seeded app_settings from AURUM_DEFAULT_CURRENCY. The seed
now keeps an existing row's alert thresholds but restores its currency to
USD, while AURUM_DEFAULT_CURRENCY controls only the starter account.
"""
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.seed import seed_default_app_settings
from app.models.settings import AppSettings


async def test_seed_creates_the_row_in_usd(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "default_currency", "GBP")

    async with test_sessionmaker() as session:
        await session.execute(delete(AppSettings))
        await session.commit()

        await seed_default_app_settings(session)

        settings_row = await session.get(AppSettings, 1)
        assert settings_row is not None
        assert settings_row.currency == "USD"


async def test_seed_normalizes_existing_currency(test_sessionmaker, monkeypatch):
    """Existing settings remain in place, but old display currencies are
    normalized to USD when the app starts."""
    async with test_sessionmaker() as session:
        existing = await session.get(AppSettings, 1)
        existing.currency = "EUR"
        await session.commit()

    monkeypatch.setattr(get_settings(), "default_currency", "GBP")

    async with test_sessionmaker() as session:
        await seed_default_app_settings(session)

        settings_row = await session.get(AppSettings, 1)
        assert settings_row.currency == "USD"
