"""Fills the database with realistic mock data for local UI testing.

Run it against a running stack with:

    docker compose exec backend python -m scripts.seed_mock_data

It replaces any existing transactions/assets/extra accounts with a fresh,
deterministic (random.seed'd) five-month dataset — the default "Main
Account" and the auto-seeded categories are kept. Safe to re-run any time
you want a clean demo dataset again.
"""
import asyncio
import random
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models import Account, Asset, AssetValuation, Category, Transaction
from app.models.enums import AccountType, AssetClass, TransactionType

random.seed(42)

TODAY = date.today()


def _shift_month(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    return date(d.year + month_index // 12, month_index % 12 + 1, 1)


# Five months of history, ending with the current (partial) month.
_current_month_start = date(TODAY.year, TODAY.month, 1)
MONTH_STARTS = [_shift_month(_current_month_start, -i) for i in range(4, -1, -1)]


def day_in_month(month_start: date, day: int) -> date | None:
    try:
        d = date(month_start.year, month_start.month, day)
    except ValueError:
        return None
    return d if d <= TODAY else None


def amount(lo: float, hi: float) -> Decimal:
    return Decimal(str(round(random.uniform(lo, hi), 2)))


async def wipe_mock_data(session) -> Account:
    """Clears prior transactions/assets/extra accounts, keeps the default
    seeded account + categories."""
    await session.execute(delete(Transaction))
    await session.execute(delete(AssetValuation))
    await session.execute(delete(Asset))
    await session.execute(delete(Account).where(Account.name != "Main Account"))
    await session.commit()

    result = await session.execute(select(Account).where(Account.name == "Main Account"))
    main_account = result.scalar_one_or_none()
    if main_account is None:
        main_account = Account(name="Main Account", type=AccountType.CHECKING, currency="USD", color="#2a78d6")
        session.add(main_account)
        await session.flush()
    return main_account


async def seed_transactions(session, main_account: Account, savings: Account, credit_card: Account) -> None:
    categories_result = await session.execute(select(Category))
    categories = {c.name: c for c in categories_result.scalars().all()}

    for month_start in MONTH_STARTS:
        # --- income ---
        salary_date = day_in_month(month_start, 1)
        if salary_date:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    category_id=categories["Salary"].id,
                    type=TransactionType.INCOME,
                    amount=amount(8200, 8800),
                    description="Salary",
                    date=salary_date,
                )
            )
        freelance_date = day_in_month(month_start, 15)
        if freelance_date and month_start.month % 2 == 0:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    category_id=categories["Freelance"].id,
                    type=TransactionType.INCOME,
                    amount=amount(500, 1500),
                    description="Freelance project",
                    date=freelance_date,
                )
            )

        # --- expenses on the main (cash) account ---
        rent_date = day_in_month(month_start, 2)
        if rent_date:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    category_id=categories["Housing & Utilities"].id,
                    type=TransactionType.EXPENSE,
                    amount=amount(2500, 2750),
                    description="Rent & utilities",
                    date=rent_date,
                )
            )

        for day, desc in [(4, "Groceries"), (11, "Groceries"), (18, "Groceries"), (25, "Groceries")]:
            d = day_in_month(month_start, day)
            if d:
                session.add(
                    Transaction(
                        account_id=main_account.id,
                        category_id=categories["Groceries"].id,
                        type=TransactionType.EXPENSE,
                        amount=amount(45, 95),
                        description=desc,
                        date=d,
                    )
                )

        for day, desc in [(3, "Restaurant"), (9, "Coffee shop"), (16, "Restaurant"), (23, "Takeout")]:
            d = day_in_month(month_start, day)
            if d:
                session.add(
                    Transaction(
                        account_id=main_account.id,
                        category_id=categories["Dining Out"].id,
                        type=TransactionType.EXPENSE,
                        amount=amount(15, 70),
                        description=desc,
                        date=d,
                    )
                )

        for day in (5, 15, 25):
            d = day_in_month(month_start, day)
            if d:
                session.add(
                    Transaction(
                        account_id=main_account.id,
                        category_id=categories["Transportation"].id,
                        type=TransactionType.EXPENSE,
                        amount=amount(35, 90),
                        description="Gas",
                        date=d,
                    )
                )

        gym_date = day_in_month(month_start, 6)
        if gym_date:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    category_id=categories["Health & Fitness"].id,
                    type=TransactionType.EXPENSE,
                    amount=amount(50, 90),
                    description="Gym membership",
                    date=gym_date,
                )
            )

        movie_date = day_in_month(month_start, 22)
        if movie_date:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    category_id=categories["Entertainment"].id,
                    type=TransactionType.EXPENSE,
                    amount=amount(15, 55),
                    description="Movies",
                    date=movie_date,
                )
            )

        subs_date = day_in_month(month_start, 1)
        if subs_date:
            for desc, value in [("Netflix", "15.99"), ("Spotify", "10.99"), ("Cloud storage", "9.99")]:
                session.add(
                    Transaction(
                        account_id=main_account.id,
                        category_id=categories["Subscriptions"].id,
                        type=TransactionType.EXPENSE,
                        amount=Decimal(value),
                        description=desc,
                        date=subs_date,
                    )
                )

        # --- expenses on the credit card (excluded from Net Worth's Cash total) ---
        cc_shopping_date = day_in_month(month_start, 20)
        if cc_shopping_date:
            session.add(
                Transaction(
                    account_id=credit_card.id,
                    category_id=categories["Shopping"].id,
                    type=TransactionType.EXPENSE,
                    amount=amount(60, 220),
                    description="Online shopping",
                    date=cc_shopping_date,
                )
            )
        cc_dining_date = day_in_month(month_start, 10)
        if cc_dining_date:
            session.add(
                Transaction(
                    account_id=credit_card.id,
                    category_id=categories["Dining Out"].id,
                    type=TransactionType.EXPENSE,
                    amount=amount(20, 60),
                    description="Dinner out",
                    date=cc_dining_date,
                )
            )

        # --- monthly transfer to savings ---
        transfer_date = day_in_month(month_start, 27)
        if transfer_date:
            session.add(
                Transaction(
                    account_id=main_account.id,
                    transfer_account_id=savings.id,
                    type=TransactionType.TRANSFER,
                    amount=amount(800, 1500),
                    description="Move to savings",
                    date=transfer_date,
                )
            )

    for row in session.new:
        if isinstance(row, Transaction):
            row.currency = "USD"
            row.fx_rate_to_usd = Decimal("1")
            row.fx_rate_date = row.date
            row.amount_usd = row.amount
            row.account_amount = row.amount
            row.transfer_amount = row.amount if row.type == TransactionType.TRANSFER else None
    await session.commit()


async def seed_assets(session) -> None:
    def d(year: int, month: int, day: int) -> date:
        return min(date(year, month, day), TODAY)

    assets_plan = [
        (
            "Brokerage account",
            AssetClass.INVESTMENTS,
            [
                (d(2026, 4, 1), "380000.00"),
                (d(2026, 5, 1), "392000.00"),
                (d(2026, 6, 1), "405000.00"),
                (d(2026, 7, 1), "415000.00"),
                (d(2026, 8, 1), "422910.43"),
                (d(2026, 8, 14), "428500.00"),
            ],
        ),
        (
            "Bitcoin",
            AssetClass.CRYPTO,
            [
                (d(2026, 4, 1), "3000.00"),
                (d(2026, 5, 1), "3800.00"),
                (d(2026, 6, 1), "3200.00"),
                (d(2026, 7, 1), "4100.00"),
                (d(2026, 8, 1), "3500.00"),
                (d(2026, 8, 14), "3900.00"),
            ],
        ),
        (
            "Apartment",
            AssetClass.REAL_ESTATE,
            [
                (d(2026, 4, 1), "345000.00"),
                (d(2026, 7, 1), "348000.00"),
                (d(2026, 8, 1), "350000.00"),
            ],
        ),
        (
            "Car",
            AssetClass.VEHICLES,
            [
                (d(2026, 4, 1), "24000.00"),
                (d(2026, 6, 1), "23200.00"),
                (d(2026, 8, 1), "22500.00"),
            ],
        ),
        (
            "Emergency fund (gold coins)",
            AssetClass.OTHER,
            [
                (d(2026, 4, 1), "1500.00"),
                (d(2026, 8, 1), "2000.00"),
            ],
        ),
    ]

    for name, asset_class, valuations in assets_plan:
        asset = Asset(name=name, asset_class=asset_class, currency="USD")
        session.add(asset)
        await session.flush()
        seen_dates: set[date] = set()
        for as_of_date, value in valuations:
            if as_of_date in seen_dates:
                continue
            seen_dates.add(as_of_date)
            session.add(AssetValuation(asset_id=asset.id, value=Decimal(value), as_of_date=as_of_date))

    await session.commit()


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print("Wiping prior mock data (transactions, assets, extra accounts)...")
        main_account = await wipe_mock_data(session)

        savings = Account(name="Savings", type=AccountType.SAVINGS, currency="USD", color="#1baf7a")
        credit_card = Account(name="Credit Card", type=AccountType.CREDIT_CARD, currency="USD", color="#e34948")
        session.add_all([savings, credit_card])
        await session.commit()
        await session.refresh(savings)
        await session.refresh(credit_card)

        print(f"Seeding transactions for {len(MONTH_STARTS)} months...")
        await seed_transactions(session, main_account, savings, credit_card)

        print("Seeding assets and valuation history...")
        await seed_assets(session)

        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
