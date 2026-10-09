"""plate numbers: Latin look-alike letters to Cyrillic

Revision ID: f1a2b3c4d5e6
Revises: c4e8a2f6d1b3
Create Date: 2026-10-09 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'c4e8a2f6d1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same mapping as app.core.plate.normalize_plate, so search finds old rows too.
    op.execute(
        "UPDATE vehicles SET plate_number = translate(upper(plate_number), 'ABEKMHOPCTYX', 'АВЕКМНОРСТУХ')"
    )


def downgrade() -> None:
    # Data-only change: the original alphabet of each plate is not recoverable.
    pass
