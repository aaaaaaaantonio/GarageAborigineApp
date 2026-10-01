"""work_catalog: GIN trigram index on name

Revision ID: b7d2e9f4a6c1
Revises: a3f5c1e8d2b4
Create Date: 2026-10-01 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d2e9f4a6c1'
down_revision: Union[str, Sequence[str], None] = 'a3f5c1e8d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        'ix_work_catalog_name_trgm',
        'work_catalog',
        ['name'],
        postgresql_using='gin',
        postgresql_ops={'name': 'gin_trgm_ops'},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_work_catalog_name_trgm', table_name='work_catalog')
