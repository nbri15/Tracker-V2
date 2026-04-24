"""Add editable pupil profile notes fields.

Revision ID: 20260424_01
Revises: 20260423_01
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = '20260424_01'
down_revision = '20260423_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pupils', sa.Column('strengths_notes', sa.Text(), nullable=True))
    op.add_column('pupils', sa.Column('next_steps_notes', sa.Text(), nullable=True))
    op.add_column('pupils', sa.Column('general_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('pupils', 'general_notes')
    op.drop_column('pupils', 'next_steps_notes')
    op.drop_column('pupils', 'strengths_notes')
