"""telegram_id columns: Integer -> BigInteger

Telegram user IDs no longer fit in int32 for newer accounts.

Revision ID: c4e8a2f6d1b3
Revises: b7d2e9f4a6c1
Create Date: 2026-10-02 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a2f6d1b3'
down_revision: Union[str, Sequence[str], None] = 'b7d2e9f4a6c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('users', 'clients', 'consents')


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.alter_column(
            table, 'telegram_id',
            existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Fails if any stored ID exceeds int32 — intentional, no silent truncation.
    for table in TABLES:
        op.alter_column(
            table, 'telegram_id',
            existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True,
        )
