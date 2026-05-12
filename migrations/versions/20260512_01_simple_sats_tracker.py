"""Simple Year 6 SATs tracker schema.

Revision ID: 20260512_01
Revises: 20260511_01_school_class_unique_per_school
"""
from alembic import op
import sqlalchemy as sa

revision = '20260512_01'
down_revision = '20260511_01_school_class_unique_per_school'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sats_exam_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('exam_number', sa.Integer(), nullable=False),
        sa.Column('arithmetic_max', sa.Integer(), nullable=False, server_default='40'),
        sa.Column('reasoning_1_max', sa.Integer(), nullable=False, server_default='35'),
        sa.Column('reasoning_2_max', sa.Integer(), nullable=False, server_default='35'),
        sa.Column('reading_max', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('spelling_max', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('grammar_max', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('school_id', 'academic_year', 'exam_number', name='uq_sats_exam_settings_scope'),
    )
    with op.batch_alter_table('sats_results') as batch_op:
        batch_op.add_column(sa.Column('exam_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('arithmetic_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reasoning_1_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reasoning_2_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('maths_combined_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('maths_scaled_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reading_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reading_scaled_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('spelling_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('grammar_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('spag_combined_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('spag_scaled_score', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_sats_result_exam_scope', ['school_id', 'pupil_id', 'academic_year', 'exam_number'])


def downgrade():
    with op.batch_alter_table('sats_results') as batch_op:
        batch_op.drop_constraint('uq_sats_result_exam_scope', type_='unique')
        for col in ['spag_scaled_score','spag_combined_score','grammar_score','spelling_score','reading_scaled_score','reading_score','maths_scaled_score','maths_combined_score','reasoning_2_score','reasoning_1_score','arithmetic_score','exam_number']:
            batch_op.drop_column(col)
    op.drop_table('sats_exam_settings')
