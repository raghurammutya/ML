"""Add broker credential columns to trading_accounts

Revision ID: 003
Revises: 002
Create Date: 2025-11-07 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trading_accounts") as batch_op:
        batch_op.add_column(sa.Column("broker_user_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("account_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("api_key_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("api_secret_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("access_token_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("password_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))

    # Populate account_name from nickname where available
    op.execute(
        """
        UPDATE trading_accounts
        SET account_name = COALESCE(account_name, nickname)
        """
    )

    op.create_index(
        "ix_trading_accounts_broker_user_id",
        "trading_accounts",
        ["broker_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trading_accounts_broker_user_id", table_name="trading_accounts")
    with op.batch_alter_table("trading_accounts") as batch_op:
        batch_op.drop_column("totp_secret_encrypted")
        batch_op.drop_column("password_encrypted")
        batch_op.drop_column("access_token_encrypted")
        batch_op.drop_column("api_secret_encrypted")
        batch_op.drop_column("api_key_encrypted")
        batch_op.drop_column("account_name")
        batch_op.drop_column("broker_user_id")
