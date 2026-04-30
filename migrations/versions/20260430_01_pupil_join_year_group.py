"""Add join_year_group to pupils.

Revision ID: 20260430_01
Revises: 20260428_01
Create Date: 2026-04-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260430_01'
down_revision = '20260428_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pupils', sa.Column('join_year_group', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('pupils', 'join_year_group')
