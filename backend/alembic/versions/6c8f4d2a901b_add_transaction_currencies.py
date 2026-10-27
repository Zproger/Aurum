"""Add transaction currencies and booked amounts.

Legacy rows had no currency or conversion metadata. Their old amount is
preserved as the USD reporting amount so every historical report retains its
previous numbers. The original currency is taken from the source account;
legacy non-USD rows must be reviewed before their USD figures can be trusted.
"""
from alembic import op
import sqlalchemy as sa

revision: str = "6c8f4d2a901b"
down_revision: str | None = "d1a6f4c8b729"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_to_usd", sa.Numeric(24, 12), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.add_column("transactions", sa.Column("amount_usd", sa.Numeric(18, 2), nullable=True))
    op.add_column("transactions", sa.Column("account_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column("transactions", sa.Column("transfer_amount", sa.Numeric(18, 2), nullable=True))
    op.execute("""
        UPDATE transactions AS t SET
            currency = a.currency,
            fx_rate_to_usd = 1,
            fx_rate_date = t.date,
            amount_usd = t.amount,
            account_amount = t.amount,
            transfer_amount = CASE WHEN t.type = 'TRANSFER' THEN t.amount ELSE NULL END
        FROM accounts AS a WHERE a.id = t.account_id
    """)
    for name in ("currency", "fx_rate_to_usd", "fx_rate_date", "amount_usd", "account_amount"):
        op.alter_column("transactions", name, nullable=False)
    op.add_column("transaction_splits", sa.Column("amount_usd", sa.Numeric(18, 2), nullable=True))
    op.execute("UPDATE transaction_splits SET amount_usd = amount")
    op.alter_column("transaction_splits", "amount_usd", nullable=False)
    op.add_column("recurring_transactions", sa.Column("currency", sa.String(3), nullable=True))
    op.execute("""
        UPDATE recurring_transactions AS r SET currency = a.currency
        FROM accounts AS a WHERE a.id = r.account_id
    """)
    op.alter_column("recurring_transactions", "currency", nullable=False)
    op.add_column("crypto_transactions", sa.Column("price_per_unit_original", sa.Numeric(38, 18), nullable=True))
    op.add_column("crypto_transactions", sa.Column("price_currency", sa.String(3), nullable=True))
    op.add_column("crypto_transactions", sa.Column("fx_rate_to_usd", sa.Numeric(24, 12), nullable=True))
    op.add_column("crypto_transactions", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.execute("""
        UPDATE crypto_transactions SET
            price_per_unit_original = price_per_unit,
            price_currency = 'USD',
            fx_rate_to_usd = 1,
            fx_rate_date = date
    """)
    for name in ("price_per_unit_original", "price_currency", "fx_rate_to_usd", "fx_rate_date"):
        op.alter_column("crypto_transactions", name, nullable=False)
    op.execute("UPDATE app_settings SET currency = 'USD'")


def downgrade() -> None:
    op.drop_column("transaction_splits", "amount_usd")
    for name in ("fx_rate_date", "fx_rate_to_usd", "price_currency", "price_per_unit_original"):
        op.drop_column("crypto_transactions", name)
    op.drop_column("recurring_transactions", "currency")
    for name in ("transfer_amount", "account_amount", "amount_usd", "fx_rate_date", "fx_rate_to_usd", "currency"):
        op.drop_column("transactions", name)
