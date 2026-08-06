"""add cable profile flat dimensions

Revision ID: 5a60abdc7ad8
Revises: d715928b9593
Create Date: 2026-08-06 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a60abdc7ad8'
down_revision: Union[str, None] = 'd715928b9593'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IS 694:2010 cl.22, Table 10 reports a flat cable's overall dimensions
    # as Width x Height, not a single diameter -- overall_diameter_mm and
    # diameter_under_sheath_mm (Round-only) can't represent a flat
    # cross-section. Separate columns, not a relabelling of the existing
    # ones.
    with op.batch_alter_table('cable_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('flat_width_mm', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('flat_height_mm', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cable_profiles', schema=None) as batch_op:
        batch_op.drop_column('flat_height_mm')
        batch_op.drop_column('flat_width_mm')
