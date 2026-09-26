"""visit_work_items created_at

Revision ID: e4a1c7d2b9f0
Revises: b70a78b9ffdd
Create Date: 2026-09-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a1c7d2b9f0'
down_revision: Union[str, Sequence[str], None] = 'b70a78b9ffdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'visit_work_items',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('visit_work_items', 'created_at')
