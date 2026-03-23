"""Add source to writing results.

Revision ID: 20260323_01_writing_result_source
Revises: 20260320_02_gap_question_papers
Create Date: 2026-03-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260323_01_writing_result_source'
down_revision = '20260320_02_gap_question_papers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('writing_results', sa.Column('source', sa.String(length=20), nullable=True))
    op.execute("UPDATE writing_results SET source = 'manual' WHERE source IS NULL")


def downgrade() -> None:
    op.drop_column('writing_results', 'source')
