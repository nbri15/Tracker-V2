"""Add assessment year group to subject results.

Revision ID: 20260423_01
Revises: 20260422_01
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = '20260423_01'
down_revision = '20260422_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subject_results', sa.Column('assessment_year_group', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('subject_results', 'assessment_year_group')
