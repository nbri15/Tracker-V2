"""standalone maths fundamentals module

Revision ID: 20260611_01_maths_fundamentals
Revises: 20260530_01_performance_indexes
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa

revision = '20260611_01_maths_fundamentals'
down_revision = '20260530_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maths_fundamental_strands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_maths_fundamental_strands_name', 'maths_fundamental_strands', ['name'])
    op.create_index('ix_maths_fundamental_strands_display_order', 'maths_fundamental_strands', ['display_order'])
    op.create_index('ix_maths_fundamental_strands_is_active', 'maths_fundamental_strands', ['is_active'])

    op.create_table(
        'maths_fundamental_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('band', sa.String(length=80), nullable=True),
        sa.Column('skill_text', sa.Text(), nullable=False),
        sa.Column('teaching_prompt', sa.Text(), nullable=True),
        sa.Column('question_prompt', sa.Text(), nullable=True),
        sa.Column('question_type', sa.String(length=80), nullable=True),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['strand_id'], ['maths_fundamental_strands.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_maths_fundamental_skills_strand_id', 'maths_fundamental_skills', ['strand_id'])
    op.create_index('ix_maths_fundamental_skills_level', 'maths_fundamental_skills', ['level'])
    op.create_index('ix_mf_skills_strand_level_order', 'maths_fundamental_skills', ['strand_id', 'level', 'display_order'])

    op.create_table(
        'maths_question_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('generator_type', sa.String(length=80), nullable=False, server_default='template'),
        sa.Column('template_text', sa.Text(), nullable=False),
        sa.Column('generator_config_json', sa.Text(), nullable=True),
        sa.Column('answer_type', sa.String(length=80), nullable=False, server_default='text'),
        sa.Column('difficulty', sa.String(length=40), nullable=False, server_default='standard'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['skill_id'], ['maths_fundamental_skills.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_maths_question_templates_skill_id', 'maths_question_templates', ['skill_id'])
    op.create_index('ix_maths_question_templates_is_active', 'maths_question_templates', ['is_active'])

    op.create_table(
        'maths_fundamentals_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=True),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('starting_level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('questions_per_level', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('group_name', sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['school_classes.id']),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['strand_id'], ['maths_fundamental_strands.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['school_id', 'teacher_id', 'class_id', 'strand_id', 'academic_year', 'is_open']:
        op.create_index(f'ix_maths_fundamentals_sessions_{col}', 'maths_fundamentals_sessions', [col])
    op.create_index('ix_mf_sessions_school_class_open', 'maths_fundamentals_sessions', ['school_id', 'class_id', 'is_open'])

    op.create_table(
        'maths_fundamental_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('current_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_skill_id', sa.Integer(), nullable=True),
        sa.Column('last_assessed', sa.DateTime(), nullable=True),
        sa.Column('next_step', sa.Text(), nullable=True),
        sa.Column('teacher_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['current_skill_id'], ['maths_fundamental_skills.id']),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['strand_id'], ['maths_fundamental_strands.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'pupil_id', 'academic_year', 'strand_id', name='uq_mf_result_pupil_year_strand'),
    )
    for col in ['school_id', 'pupil_id', 'academic_year', 'strand_id']:
        op.create_index(f'ix_maths_fundamental_results_{col}', 'maths_fundamental_results', [col])
    op.create_index('ix_mf_results_school_year_strand', 'maths_fundamental_results', ['school_id', 'academic_year', 'strand_id'])

    op.create_table(
        'maths_fundamental_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('final_level', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='in_progress'),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('current_level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('questions_per_level', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['session_id'], ['maths_fundamentals_sessions.id']),
        sa.ForeignKeyConstraint(['strand_id'], ['maths_fundamental_strands.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['school_id', 'pupil_id', 'strand_id', 'academic_year', 'status', 'session_id']:
        op.create_index(f'ix_maths_fundamental_attempts_{col}', 'maths_fundamental_attempts', [col])
    op.create_index('ix_mf_attempt_school_pupil_year', 'maths_fundamental_attempts', ['school_id', 'pupil_id', 'academic_year'])

    op.create_table(
        'maths_fundamental_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attempt_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('correct_answer', sa.String(length=255), nullable=True),
        sa.Column('pupil_answer', sa.String(length=255), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('teacher_mark_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('answered_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['attempt_id'], ['maths_fundamental_attempts.id']),
        sa.ForeignKeyConstraint(['skill_id'], ['maths_fundamental_skills.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ['attempt_id', 'skill_id', 'level']:
        op.create_index(f'ix_maths_fundamental_questions_{col}', 'maths_fundamental_questions', [col])

    op.create_table(
        'pupil_qr_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=96), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'pupil_id', name='uq_pupil_qr_token_pupil'),
        sa.UniqueConstraint('token', name='uq_pupil_qr_token_token'),
    )
    for col in ['school_id', 'pupil_id', 'token', 'is_active']:
        op.create_index(f'ix_pupil_qr_tokens_{col}', 'pupil_qr_tokens', [col])


def downgrade():
    op.drop_table('pupil_qr_tokens')
    op.drop_table('maths_fundamental_questions')
    op.drop_table('maths_fundamental_attempts')
    op.drop_table('maths_fundamental_results')
    op.drop_table('maths_fundamentals_sessions')
    op.drop_table('maths_question_templates')
    op.drop_table('maths_fundamental_skills')
    op.drop_table('maths_fundamental_strands')
