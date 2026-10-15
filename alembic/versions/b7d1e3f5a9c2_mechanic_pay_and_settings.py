"""mechanic pay scheme, pay snapshot on work items, app settings

Revision ID: b7d1e3f5a9c2
Revises: a9c3e5f7b1d2
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1e3f5a9c2'
down_revision: Union[str, Sequence[str], None] = 'a9c3e5f7b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

payscheme = sa.Enum('PERCENT', 'PER_HOUR', 'FULL', name='payscheme')


def upgrade() -> None:
    """Upgrade schema."""
    payscheme.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column('pay_scheme', payscheme, nullable=True))
    op.add_column('users', sa.Column('pay_value', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('visit_work_items', sa.Column('mechanic_pay', sa.Numeric(precision=10, scale=2), nullable=True))
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('app_settings')
    op.drop_column('visit_work_items', 'mechanic_pay')
    op.drop_column('users', 'pay_value')
    op.drop_column('users', 'pay_scheme')
    payscheme.drop(op.get_bind(), checkfirst=True)
