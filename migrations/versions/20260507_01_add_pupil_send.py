"""add send flag to pupils

Revision ID: 20260507_01_add_pupil_send
Revises: 20260430_02_pupil_join_date
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = '20260507_01_add_pupil_send'
down_revision = '20260430_02_pupil_join_date'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pupils', sa.Column('send', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('pupils', 'send', server_default=None)


def downgrade() -> None:
    op.drop_column('pupils', 'send')
