"""add network field to crypto holdings

Revision ID: d1a6f4c8b729
Revises: c4e8f61a9d23
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a6f4c8b729'
down_revision: Union[str, None] = 'c4e8f61a9d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crypto_holdings', sa.Column('network', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('crypto_holdings', 'network')
