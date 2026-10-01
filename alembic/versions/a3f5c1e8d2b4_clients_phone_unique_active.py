"""clients: unique phone_normalized among active clients

Revision ID: a3f5c1e8d2b4
Revises: e4a1c7d2b9f0
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f5c1e8d2b4'
down_revision: Union[str, Sequence[str], None] = 'e4a1c7d2b9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'uq_clients_phone_normalized_active',
        'clients',
        ['phone_normalized'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_clients_phone_normalized_active', table_name='clients')
