"""add app_settings

Revision ID: 9f3a2d7c5e11
Revises: 1152a14e9d55
Create Date: 2026-08-16 12:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3a2d7c5e11'
down_revision: Union[str, None] = '1152a14e9d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _default_currency() -> str:
    """Read and validate the configured currency for a fresh database."""
    currency = os.getenv("AURUM_DEFAULT_CURRENCY", "USD").strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("AURUM_DEFAULT_CURRENCY must be a three-letter ISO 4217 code")
    return currency


def upgrade() -> None:
    default_currency = _default_currency()
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default=default_currency),
        sa.PrimaryKeyConstraint('id'),
    )
    # Singleton row (id=1) — app boot's seed_default_app_settings() also
    # get-or-creates it, but seeding it here means it exists immediately
    # after migrating, even before the app has started once. Respect the
    # configured default so non-USD installations are consistent from boot.
    settings_table = sa.table(
        'app_settings',
        sa.column('id', sa.Integer()),
        sa.column('currency', sa.String(length=3)),
    )
    op.bulk_insert(settings_table, [{'id': 1, 'currency': default_currency}])


def downgrade() -> None:
    op.drop_table('app_settings')
