"""Add per-paper assignment to GAP questions.

Revision ID: 20260320_02
Revises: 20260320_01
Create Date: 2026-03-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260320_02'
down_revision = '20260320_01'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {column['name'] for column in inspector.get_columns('gap_questions')}
    if 'paper' not in column_names:
        op.add_column('gap_questions', sa.Column('paper', sa.String(length=20), nullable=True))
    op.execute("UPDATE gap_questions SET paper = 'paper_1' WHERE paper IS NULL")
    with op.batch_alter_table('gap_questions') as batch_op:
        batch_op.alter_column('paper', existing_type=sa.String(length=20), nullable=False)


def downgrade():
    op.drop_column('gap_questions', 'paper')
