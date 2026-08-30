"""add zenmoney integration

Revision ID: 9c4b1e8a7f23
Revises: 7b535ef9e189
Create Date: 2026-08-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c4b1e8a7f23'
down_revision: Union[str, None] = '7b535ef9e189'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('zenmoney_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_accounts_zenmoney_id'), 'accounts', ['zenmoney_id'], unique=True)

    op.add_column('categories', sa.Column('zenmoney_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_categories_zenmoney_id'), 'categories', ['zenmoney_id'], unique=True)

    op.add_column('transactions', sa.Column('zenmoney_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_transactions_zenmoney_id'), 'transactions', ['zenmoney_id'], unique=True)

    op.create_table(
        'zenmoney_sync_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('server_timestamp', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('synced_accounts_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('synced_categories_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('synced_transactions_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('zenmoney_sync_state')
    op.drop_index(op.f('ix_transactions_zenmoney_id'), table_name='transactions')
    op.drop_column('transactions', 'zenmoney_id')
    op.drop_index(op.f('ix_categories_zenmoney_id'), table_name='categories')
    op.drop_column('categories', 'zenmoney_id')
    op.drop_index(op.f('ix_accounts_zenmoney_id'), table_name='accounts')
    op.drop_column('accounts', 'zenmoney_id')
