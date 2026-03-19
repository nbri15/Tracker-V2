"""Phase 2 assessment entry schema.

Revision ID: 20260319_01
Revises:
Create Date: 2026-03-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260319_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )

    op.create_table(
        'assessment_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('term', sa.String(length=20), nullable=False),
        sa.Column('paper_1_name', sa.String(length=100), nullable=False),
        sa.Column('paper_1_max', sa.Integer(), nullable=False),
        sa.Column('paper_2_name', sa.String(length=100), nullable=False),
        sa.Column('paper_2_max', sa.Integer(), nullable=False),
        sa.Column('combined_max', sa.Integer(), nullable=False),
        sa.Column('below_are_threshold_percent', sa.Float(), nullable=False),
        sa.Column('on_track_threshold_percent', sa.Float(), nullable=False),
        sa.Column('exceeding_threshold_percent', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_group', 'subject', 'term', name='uq_assessment_setting_scope'),
    )

    op.create_table(
        'school_classes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'pupils',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=80), nullable=False),
        sa.Column('last_name', sa.String(length=80), nullable=False),
        sa.Column('gender', sa.String(length=20), nullable=False),
        sa.Column('pupil_premium', sa.Boolean(), nullable=False),
        sa.Column('laps', sa.Boolean(), nullable=False),
        sa.Column('service_child', sa.Boolean(), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['school_classes.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'interventions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('term', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'sats_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('assessment_point', sa.Integer(), nullable=False),
        sa.Column('raw_score', sa.Integer(), nullable=True),
        sa.Column('scaled_score', sa.Integer(), nullable=True),
        sa.Column('is_most_recent', sa.Boolean(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'subject_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('term', sa.String(length=20), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('paper_1_score', sa.Integer(), nullable=True),
        sa.Column('paper_2_score', sa.Integer(), nullable=True),
        sa.Column('combined_score', sa.Integer(), nullable=True),
        sa.Column('combined_percent', sa.Float(), nullable=True),
        sa.Column('band_label', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'term', 'subject', name='uq_subject_result_scope'),
    )

    op.create_table(
        'writing_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('term', sa.String(length=20), nullable=False),
        sa.Column('band', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'term', name='uq_writing_result_scope'),
    )


def downgrade():
    op.drop_table('writing_results')
    op.drop_table('subject_results')
    op.drop_table('sats_results')
    op.drop_table('interventions')
    op.drop_table('pupils')
    op.drop_table('school_classes')
    op.drop_table('assessment_settings')
    op.drop_table('users')
