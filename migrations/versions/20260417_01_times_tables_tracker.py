"""Add Year 4 times tables tracker tables.

Revision ID: 20260417_01
Revises: 20260416_02
Create Date: 2026-04-17 08:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260417_01'
down_revision = '20260416_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'times_table_test_columns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_group', 'name', name='uq_times_table_test_column_name'),
    )
    op.create_index('ix_times_table_test_columns_year_group', 'times_table_test_columns', ['year_group'])
    op.create_index('ix_times_table_test_columns_scope', 'times_table_test_columns', ['year_group', 'display_order'])

    op.create_table(
        'times_table_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('times_table_test_column_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['times_table_test_column_id'], ['times_table_test_columns.id']),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'times_table_test_column_id', name='uq_times_table_score_scope'),
    )
    op.create_index('ix_times_table_scores_pupil_id', 'times_table_scores', ['pupil_id'])
    op.create_index('ix_times_table_scores_academic_year', 'times_table_scores', ['academic_year'])
    op.create_index('ix_times_table_scores_times_table_test_column_id', 'times_table_scores', ['times_table_test_column_id'])
    op.create_index('ix_times_table_scores_lookup', 'times_table_scores', ['academic_year', 'times_table_test_column_id'])


def downgrade():
    op.drop_index('ix_times_table_scores_lookup', table_name='times_table_scores')
    op.drop_index('ix_times_table_scores_times_table_test_column_id', table_name='times_table_scores')
    op.drop_index('ix_times_table_scores_academic_year', table_name='times_table_scores')
    op.drop_index('ix_times_table_scores_pupil_id', table_name='times_table_scores')
    op.drop_table('times_table_scores')

    op.drop_index('ix_times_table_test_columns_scope', table_name='times_table_test_columns')
    op.drop_index('ix_times_table_test_columns_year_group', table_name='times_table_test_columns')
    op.drop_table('times_table_test_columns')
