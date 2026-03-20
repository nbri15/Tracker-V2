"""Phase 4 year 6 mode, flexible SATs, history, and admin hardening.

Revision ID: 20260320_01
Revises: 20260319_02
Create Date: 2026-03-20 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260320_01'
down_revision = '20260319_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tracker_mode_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('tracker_mode', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_group', name='uq_tracker_mode_year_group'),
    )
    op.create_index('ix_tracker_mode_settings_year_group', 'tracker_mode_settings', ['year_group'])

    op.create_table(
        'sats_column_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('subject', sa.String(length=40), nullable=False),
        sa.Column('max_marks', sa.Integer(), nullable=False),
        sa.Column('pass_percentage', sa.Float(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sats_column_settings_year_group', 'sats_column_settings', ['year_group'])
    op.create_index('ix_sats_column_settings_subject', 'sats_column_settings', ['subject'])
    op.create_index('ix_sats_column_year_order', 'sats_column_settings', ['year_group', 'display_order'])

    op.create_table(
        'sats_column_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('column_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('raw_score', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['column_id'], ['sats_column_settings.id']),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'column_id', 'academic_year', name='uq_sats_column_result_scope'),
    )
    op.create_index('ix_sats_column_results_pupil_id', 'sats_column_results', ['pupil_id'])
    op.create_index('ix_sats_column_results_column_id', 'sats_column_results', ['column_id'])
    op.create_index('ix_sats_column_results_academic_year', 'sats_column_results', ['academic_year'])
    op.create_index('ix_sats_column_result_lookup', 'sats_column_results', ['academic_year', 'column_id'])

    op.create_table(
        'academic_years',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'pupil_class_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('class_name', sa.String(length=120), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('teacher_username', sa.String(length=80), nullable=True),
        sa.Column('promoted_to_year_group', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', name='uq_pupil_class_history_scope'),
    )
    op.create_index('ix_pupil_class_history_pupil_id', 'pupil_class_history', ['pupil_id'])
    op.create_index('ix_pupil_class_history_academic_year', 'pupil_class_history', ['academic_year'])
    op.create_index('ix_pupil_class_history_year_group', 'pupil_class_history', ['academic_year', 'year_group'])


def downgrade():
    op.drop_index('ix_pupil_class_history_year_group', table_name='pupil_class_history')
    op.drop_index('ix_pupil_class_history_academic_year', table_name='pupil_class_history')
    op.drop_index('ix_pupil_class_history_pupil_id', table_name='pupil_class_history')
    op.drop_table('pupil_class_history')
    op.drop_table('academic_years')
    op.drop_index('ix_sats_column_result_lookup', table_name='sats_column_results')
    op.drop_index('ix_sats_column_results_academic_year', table_name='sats_column_results')
    op.drop_index('ix_sats_column_results_column_id', table_name='sats_column_results')
    op.drop_index('ix_sats_column_results_pupil_id', table_name='sats_column_results')
    op.drop_table('sats_column_results')
    op.drop_index('ix_sats_column_year_order', table_name='sats_column_settings')
    op.drop_index('ix_sats_column_settings_subject', table_name='sats_column_settings')
    op.drop_index('ix_sats_column_settings_year_group', table_name='sats_column_settings')
    op.drop_table('sats_column_settings')
    op.drop_index('ix_tracker_mode_settings_year_group', table_name='tracker_mode_settings')
    op.drop_table('tracker_mode_settings')
