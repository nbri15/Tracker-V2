"""Add join_date to pupils.

Revision ID: 20260430_02
Revises: 20260430_01
Create Date: 2026-04-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260430_02'
down_revision = '20260430_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pupils', sa.Column('join_date', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('pupils', 'join_date')
