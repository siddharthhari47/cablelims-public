"""add user token_version

Revision ID: a89f4f8f2e41
Revises: 00e595886516
Create Date: 2026-08-03 18:38:39.042769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a89f4f8f2e41'
down_revision: Union[str, None] = '00e595886516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='1' (not just the model's Python-side default=1) is
    # required here, not optional -- SQLite rejects adding a NOT NULL
    # column via ALTER TABLE without one, and this migration runs against
    # databases that already have real user rows (every install predating
    # H6). Existing accounts starting at token_version=1, matching brand-
    # new accounts, is exactly correct: nothing has been revoked for them.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')
