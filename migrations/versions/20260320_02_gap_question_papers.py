"""Add paper key to GAP questions.

Revision ID: 20260320_02_gap_question_papers
Revises: 20260320_01
Create Date: 2026-03-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260320_02_gap_question_papers'
down_revision = '20260320_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gap_questions', sa.Column('paper_key', sa.String(length=20), nullable=False, server_default='paper_1'))
    op.execute("UPDATE gap_questions SET paper_key = 'paper_1' WHERE paper_key IS NULL")


def downgrade() -> None:
    op.drop_column('gap_questions', 'paper_key')
