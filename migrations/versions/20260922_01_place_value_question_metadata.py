"""Add mastery and visual metadata for Place Value Fundamentals.

Revision ID: 20260922_01
Revises: 20260921_01

All changes are additive and nullable so existing Early Number Sense, Number
Bonds, sessions, attempts and responses remain valid.
"""

from alembic import op
import sqlalchemy as sa


revision = '20260922_01'
down_revision = '20260921_01'
branch_labels = None
depends_on = None


LEVEL_COLUMNS = (
    sa.Column('diagnostic_intent', sa.Text(), nullable=True),
    sa.Column('key_representations', sa.String(length=255), nullable=True),
    sa.Column('mastery_emphasis', sa.String(length=255), nullable=True),
)

QUESTION_COLUMNS = (
    sa.Column('skill', sa.String(length=255), nullable=True),
    sa.Column('representation_type', sa.String(length=80), nullable=True),
    sa.Column('mastery_focus', sa.String(length=80), nullable=True),
    sa.Column('rendering_notes', sa.Text(), nullable=True),
    sa.Column('visual_data', sa.JSON(), nullable=True),
)


def _add_missing_columns(table_name, columns):
    existing = {
        column['name']
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    with op.batch_alter_table(table_name) as batch_op:
        for column in columns:
            if column.name not in existing:
                batch_op.add_column(column)


def upgrade():
    _add_missing_columns('fundamental_levels', LEVEL_COLUMNS)
    _add_missing_columns('fundamental_questions', QUESTION_COLUMNS)


def downgrade():
    with op.batch_alter_table('fundamental_questions') as batch_op:
        for column in reversed(QUESTION_COLUMNS):
            batch_op.drop_column(column.name)
    with op.batch_alter_table('fundamental_levels') as batch_op:
        for column in reversed(LEVEL_COLUMNS):
            batch_op.drop_column(column.name)
