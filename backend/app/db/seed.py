"""Seeds the default category set on first boot.

The expense categories are assigned hues from the dataviz skill's validated
8-slot categorical palette, in the palette's fixed slot order (never
reordered/cycled) so the dashboard donut chart is colorblind-safe out of the
box. See CLAUDE.md-adjacent design notes in UPDATES.md for the source.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.account import Account
from app.models.category import Category
from app.models.enums import AccountType, CategoryKind
from app.models.settings import AppSettings

# (name, icon, color) — order doubles as sort_order / palette slot index.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Housing & Utilities", "home", "#2a78d6"),  # slot 1 blue
    ("Groceries", "shopping-basket", "#1baf7a"),  # slot 3 aqua
    ("Dining Out", "utensils", "#eb6834"),  # slot 2 orange
    ("Transportation", "car", "#4a3aa7"),  # slot 7 violet
    ("Health & Fitness", "heart-pulse", "#e34948"),  # slot 8 red
    ("Shopping", "shopping-bag", "#eda100"),  # slot 4 yellow
    ("Entertainment", "clapperboard", "#e87ba4"),  # slot 5 magenta
    ("Subscriptions", "repeat", "#008300"),  # slot 6 green
]

DEFAULT_INCOME_CATEGORIES = [
    ("Salary", "banknote", "#2a78d6"),
    ("Freelance", "briefcase", "#1baf7a"),
    ("Investments", "trending-up", "#4a3aa7"),
    ("Gifts", "gift", "#e87ba4"),
    ("Business Income", "building-2", "#eb6834"),
    ("Rental Income", "key", "#eda100"),
    ("Benefits", "hand-coins", "#008300"),
    ("Item Sales", "tag", "#e34948"),
    ("Other Income", "plus-circle", "#898781"),
]


async def seed_default_categories(session: AsyncSession) -> None:
    existing = await session.execute(select(Category.id).limit(1))
    if existing.first() is not None:
        return

    order = 0
    for name, icon, color in DEFAULT_EXPENSE_CATEGORIES:
        session.add(
            Category(name=name, kind=CategoryKind.EXPENSE, icon=icon, color=color, sort_order=order, is_default=True)
        )
        order += 1
    for name, icon, color in DEFAULT_INCOME_CATEGORIES:
        session.add(
            Category(name=name, kind=CategoryKind.INCOME, icon=icon, color=color, sort_order=order, is_default=True)
        )
        order += 1

    await session.commit()


async def seed_default_account(session: AsyncSession) -> None:
    """Creates one starter account so the Transactions form always has a
    destination to post to, even before the (future) accounts management UI
    ships."""
    existing = await session.execute(select(Account.id).limit(1))
    if existing.first() is not None:
        return

    session.add(
        Account(
            name="Main Account",
            type=AccountType.CHECKING,
            currency=get_settings().default_currency,
            color="#2a78d6",
        )
    )
    await session.commit()


async def seed_default_app_settings(session: AsyncSession) -> None:
    """Keep the singleton reporting currency at USD on every boot.

    The earlier configurable-currency seed remains in Git history; account
    currency is now independent of the USD reporting denomination.
    """
    existing = await session.get(AppSettings, 1)
    if existing is not None:
        if existing.currency != "USD":
            existing.currency = "USD"
            await session.commit()
        return

    session.add(AppSettings(id=1, currency="USD"))
    await session.commit()
