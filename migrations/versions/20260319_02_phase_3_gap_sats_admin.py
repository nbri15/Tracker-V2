"""Phase 3 GAP, SATs, import, and admin schema.

Revision ID: 20260319_02
Revises: 20260319_01
Create Date: 2026-03-19 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260319_02'
down_revision = '20260319_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('interventions', sa.Column('academic_year', sa.String(length=20), nullable=True))
    op.add_column('interventions', sa.Column('auto_flagged', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_interventions_scope', 'interventions', ['subject', 'term', 'academic_year', 'is_active'])

    op.execute("UPDATE interventions SET academic_year = '2025/26' WHERE academic_year IS NULL")
    with op.batch_alter_table('interventions') as batch_op:
        batch_op.alter_column('academic_year', existing_type=sa.String(length=20), nullable=False)

    op.create_table(
        'gap_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('term', sa.String(length=20), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=True),
        sa.Column('paper_name', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_group', 'subject', 'term', 'academic_year', name='uq_gap_template_scope'),
    )
    op.create_index('ix_gap_templates_year_group', 'gap_templates', ['year_group'])
    op.create_index('ix_gap_templates_subject', 'gap_templates', ['subject'])
    op.create_index('ix_gap_templates_term', 'gap_templates', ['term'])
    op.create_index('ix_gap_templates_academic_year', 'gap_templates', ['academic_year'])

    op.create_table(
        'gap_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('question_label', sa.String(length=20), nullable=False),
        sa.Column('question_type', sa.String(length=120), nullable=True),
        sa.Column('max_score', sa.Integer(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['gap_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gap_questions_template_order', 'gap_questions', ['template_id', 'display_order'])

    op.create_table(
        'gap_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.ForeignKeyConstraint(['question_id'], ['gap_questions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'question_id', name='uq_gap_score_scope'),
    )
    op.create_index('ix_gap_scores_pupil_question', 'gap_scores', ['pupil_id', 'question_id'])

    op.create_table(
        'sats_writing_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('assessment_point', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('band', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'assessment_point', 'academic_year', name='uq_sats_writing_scope'),
    )
    op.create_index('ix_sats_writing_lookup', 'sats_writing_results', ['academic_year', 'assessment_point'])

    op.create_index('ix_subject_results_lookup', 'subject_results', ['academic_year', 'term', 'subject'])
    op.create_index('ix_sats_result_lookup', 'sats_results', ['academic_year', 'subject', 'assessment_point'])


def downgrade():
    op.drop_index('ix_sats_result_lookup', table_name='sats_results')
    op.drop_index('ix_subject_results_lookup', table_name='subject_results')
    op.drop_index('ix_sats_writing_lookup', table_name='sats_writing_results')
    op.drop_table('sats_writing_results')
    op.drop_index('ix_gap_scores_pupil_question', table_name='gap_scores')
    op.drop_table('gap_scores')
    op.drop_index('ix_gap_questions_template_order', table_name='gap_questions')
    op.drop_table('gap_questions')
    op.drop_index('ix_gap_templates_academic_year', table_name='gap_templates')
    op.drop_index('ix_gap_templates_term', table_name='gap_templates')
    op.drop_index('ix_gap_templates_subject', table_name='gap_templates')
    op.drop_index('ix_gap_templates_year_group', table_name='gap_templates')
    op.drop_table('gap_templates')
    op.drop_index('ix_interventions_scope', table_name='interventions')
    op.drop_column('interventions', 'auto_flagged')
    op.drop_column('interventions', 'academic_year')
