"""Add KS1 phonics tracker tables.

Revision ID: 20260416_02
Revises: 20260416_01
Create Date: 2026-04-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260416_02'
down_revision = '20260416_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'phonics_test_columns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_group', 'name', name='uq_phonics_test_column_name'),
    )
    op.create_index('ix_phonics_test_columns_year_group', 'phonics_test_columns', ['year_group'])
    op.create_index('ix_phonics_test_columns_scope', 'phonics_test_columns', ['year_group', 'display_order'])

    op.create_table(
        'phonics_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('phonics_test_column_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['phonics_test_column_id'], ['phonics_test_columns.id']),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'phonics_test_column_id', name='uq_phonics_score_scope'),
    )
    op.create_index('ix_phonics_scores_pupil_id', 'phonics_scores', ['pupil_id'])
    op.create_index('ix_phonics_scores_academic_year', 'phonics_scores', ['academic_year'])
    op.create_index('ix_phonics_scores_phonics_test_column_id', 'phonics_scores', ['phonics_test_column_id'])
    op.create_index('ix_phonics_scores_lookup', 'phonics_scores', ['academic_year', 'phonics_test_column_id'])


def downgrade():
    op.drop_index('ix_phonics_scores_lookup', table_name='phonics_scores')
    op.drop_index('ix_phonics_scores_phonics_test_column_id', table_name='phonics_scores')
    op.drop_index('ix_phonics_scores_academic_year', table_name='phonics_scores')
    op.drop_index('ix_phonics_scores_pupil_id', table_name='phonics_scores')
    op.drop_table('phonics_scores')

    op.drop_index('ix_phonics_test_columns_scope', table_name='phonics_test_columns')
    op.drop_index('ix_phonics_test_columns_year_group', table_name='phonics_test_columns')
    op.drop_table('phonics_test_columns')
