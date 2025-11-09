"""baseline - existing database schema

This migration represents the baseline state of the database as of 2025-11-09.
All existing tables and structures are already in place from manual SQL migrations.

This is a no-op migration that marks the current database state as the starting point
for Alembic-managed migrations going forward.

Existing migrations applied (migrations/*.sql):
- 001-028: Various feature migrations
- 029: Statement tables (funds management)

Revision ID: b80c16c4db24
Revises:
Create Date: 2025-11-09 08:43:07.937913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b80c16c4db24'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    This is a baseline migration - no changes to apply.
    All tables already exist in the database.
    """
    pass


def downgrade() -> None:
    """
    Baseline cannot be downgraded.
    """
    pass
