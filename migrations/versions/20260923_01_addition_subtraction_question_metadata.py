"""Preserve Addition & Subtraction question metadata.

Revision ID: 20260923_01
Revises: 20260922_01

The nullable, additive columns retain workbook answer and diagnostic metadata
without changing existing strands, attempts, responses or result snapshots.
"""

from alembic import op
import sqlalchemy as sa


revision = '20260923_01'
down_revision = '20260922_01'
branch_labels = None
depends_on = None


QUESTION_COLUMNS = (
    sa.Column('answer_type', sa.String(length=20), nullable=True),
    sa.Column('renderer_spec', sa.Text(), nullable=True),
    sa.Column('stem_reasoning_prompt', sa.Text(), nullable=True),
    sa.Column('misconception_target', sa.Text(), nullable=True),
    sa.Column('accepted_answers', sa.JSON(), nullable=True),
)


def upgrade():
    existing = {
        column['name']
        for column in sa.inspect(op.get_bind()).get_columns('fundamental_questions')
    }
    with op.batch_alter_table('fundamental_questions') as batch_op:
        for column in QUESTION_COLUMNS:
            if column.name not in existing:
                batch_op.add_column(column)


def downgrade():
    existing = {
        column['name']
        for column in sa.inspect(op.get_bind()).get_columns('fundamental_questions')
    }
    with op.batch_alter_table('fundamental_questions') as batch_op:
        for column in reversed(QUESTION_COLUMNS):
            if column.name in existing:
                batch_op.drop_column(column.name)
