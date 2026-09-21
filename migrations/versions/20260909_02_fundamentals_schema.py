"""Adopt or create the Maths Fundamentals schema.

Revision ID: 20260909_02
Revises: 20260903_01

The six Fundamentals tables were previously created by application startup,
outside Alembic.  Each table is therefore created only when absent.  Existing
tables are adopted in place, checked for their required columns, and receive
only the additive response-snapshot columns and any missing constraints or
indexes.  No table or row is deleted or recreated.
"""

from alembic import op
import sqlalchemy as sa


revision = '20260909_02'
down_revision = '20260903_01'
branch_labels = None
depends_on = None


TABLES = (
    'fundamental_strands',
    'fundamental_levels',
    'fundamental_questions',
    'fundamental_sessions',
    'fundamental_pupil_attempts',
    'fundamental_responses',
)


def _inspector():
    return sa.inspect(op.get_bind())


def _require_columns(table_name, required):
    actual = {column['name'] for column in _inspector().get_columns(table_name)}
    missing = sorted(set(required) - actual)
    if missing:
        raise RuntimeError(
            f'Existing table {table_name!r} is not compatible with the current '
            f'Maths Fundamentals model; missing columns: {", ".join(missing)}. '
            'Migration stopped without deleting data.'
        )


def _index_signatures(table_name):
    return {
        (tuple(index.get('column_names') or ()), bool(index.get('unique')))
        for index in _inspector().get_indexes(table_name)
    }


def _unique_signatures(table_name):
    signatures = {
        tuple(constraint.get('column_names') or ())
        for constraint in _inspector().get_unique_constraints(table_name)
    }
    signatures.update(
        tuple(index.get('column_names') or ())
        for index in _inspector().get_indexes(table_name)
        if index.get('unique')
    )
    return signatures


def _foreign_key_signatures(table_name):
    return {
        (
            tuple(foreign_key.get('constrained_columns') or ()),
            foreign_key.get('referred_table'),
            tuple(foreign_key.get('referred_columns') or ()),
        )
        for foreign_key in _inspector().get_foreign_keys(table_name)
    }


def _ensure_index(table_name, column_name, *, unique=False):
    signature = ((column_name,), unique)
    if signature not in _index_signatures(table_name):
        op.create_index(
            f'ix_{table_name}_{column_name}',
            table_name,
            [column_name],
            unique=unique,
        )


def _ensure_unique(table_name, columns, name):
    columns = tuple(columns)
    if columns in _unique_signatures(table_name):
        return
    if _inspector().dialect.name == 'sqlite':
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(name, list(columns))
    else:
        op.create_unique_constraint(name, table_name, list(columns))


def _ensure_foreign_key(table_name, column, referred_table, *, name):
    signature = ((column,), referred_table, ('id',))
    if signature in _foreign_key_signatures(table_name):
        return
    if _inspector().dialect.name == 'sqlite':
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(name, referred_table, [column], ['id'])
    else:
        op.create_foreign_key(name, table_name, referred_table, [column], ['id'])


def _create_strands():
    op.create_table(
        'fundamental_strands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=140), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def _create_levels():
    op.create_table(
        'fundamental_levels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('level_number', sa.Integer(), nullable=False),
        sa.Column('skill', sa.String(length=255), nullable=False),
        sa.Column('expected_year', sa.String(length=80), nullable=True),
        sa.Column('pass_mark', sa.Integer(), nullable=False, server_default=sa.text('70')),
        sa.ForeignKeyConstraint(['strand_id'], ['fundamental_strands.id'], name='fk_fundamental_levels_strand_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strand_id', 'level_number', name='uq_fundamental_level_strand_number'),
    )


def _create_questions():
    op.create_table(
        'fundamental_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('level_number', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.String(length=60), nullable=False),
        sa.Column('question_type', sa.String(length=80), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('answer', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['strand_id'], ['fundamental_strands.id'], name='fk_fundamental_questions_strand_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strand_id', 'question_id', name='uq_fundamental_question_strand_question_id'),
    )


def _create_sessions():
    op.create_table(
        'fundamental_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('strand_id', sa.Integer(), nullable=False),
        sa.Column('start_level', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['class_id'], ['school_classes.id'], name='fk_fundamental_sessions_class_id'),
        sa.ForeignKeyConstraint(['strand_id'], ['fundamental_strands.id'], name='fk_fundamental_sessions_strand_id'),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], name='fk_fundamental_sessions_teacher_id'),
        sa.PrimaryKeyConstraint('id'),
    )


def _create_attempts():
    op.create_table(
        'fundamental_pupil_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('current_level', sa.Integer(), nullable=False),
        sa.Column('secure_level', sa.Integer(), nullable=True),
        sa.Column('intervention_level', sa.Integer(), nullable=True),
        sa.Column('below_70_streak', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_complete', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id'], name='fk_fundamental_pupil_attempts_pupil_id'),
        sa.ForeignKeyConstraint(['session_id'], ['fundamental_sessions.id'], name='fk_fundamental_pupil_attempts_session_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'pupil_id', name='uq_fundamental_attempt_session_pupil'),
    )


def _create_responses():
    op.create_table(
        'fundamental_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attempt_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('level_number', sa.Integer(), nullable=False),
        sa.Column('pupil_answer', sa.String(length=255), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('question_text_snapshot', sa.Text(), nullable=True),
        sa.Column('correct_answer_snapshot', sa.String(length=255), nullable=True),
        sa.Column('skill_snapshot', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['attempt_id'], ['fundamental_pupil_attempts.id'], name='fk_fundamental_responses_attempt_id'),
        sa.ForeignKeyConstraint(['question_id'], ['fundamental_questions.id'], name='fk_fundamental_responses_question_id'),
        sa.PrimaryKeyConstraint('id'),
    )


def upgrade():
    creators = (
        ('fundamental_strands', _create_strands),
        ('fundamental_levels', _create_levels),
        ('fundamental_questions', _create_questions),
        ('fundamental_sessions', _create_sessions),
        ('fundamental_pupil_attempts', _create_attempts),
        ('fundamental_responses', _create_responses),
    )
    for table_name, creator in creators:
        if not _inspector().has_table(table_name):
            creator()

    required_columns = {
        'fundamental_strands': ('id', 'code', 'name', 'description'),
        'fundamental_levels': ('id', 'strand_id', 'level_number', 'skill', 'expected_year', 'pass_mark'),
        'fundamental_questions': ('id', 'strand_id', 'level_number', 'question_id', 'question_type', 'question_text', 'answer'),
        'fundamental_sessions': ('id', 'class_id', 'teacher_id', 'strand_id', 'start_level', 'is_active', 'created_at'),
        'fundamental_pupil_attempts': (
            'id', 'session_id', 'pupil_id', 'current_level', 'secure_level',
            'intervention_level', 'below_70_streak', 'is_complete', 'created_at', 'completed_at',
        ),
        'fundamental_responses': (
            'id', 'attempt_id', 'question_id', 'level_number', 'pupil_answer', 'is_correct', 'created_at',
        ),
    }
    for table_name, columns in required_columns.items():
        _require_columns(table_name, columns)

    response_columns = {
        column['name'] for column in _inspector().get_columns('fundamental_responses')
    }
    for column in (
        sa.Column('question_text_snapshot', sa.Text(), nullable=True),
        sa.Column('correct_answer_snapshot', sa.String(length=255), nullable=True),
        sa.Column('skill_snapshot', sa.String(length=255), nullable=True),
    ):
        if column.name not in response_columns:
            op.add_column('fundamental_responses', column)

    _ensure_unique('fundamental_levels', ('strand_id', 'level_number'), 'uq_fundamental_level_strand_number')
    _ensure_unique('fundamental_questions', ('strand_id', 'question_id'), 'uq_fundamental_question_strand_question_id')
    _ensure_unique('fundamental_pupil_attempts', ('session_id', 'pupil_id'), 'uq_fundamental_attempt_session_pupil')

    for table_name, column_name, unique in (
        ('fundamental_strands', 'code', True),
        ('fundamental_levels', 'strand_id', False),
        ('fundamental_levels', 'level_number', False),
        ('fundamental_questions', 'strand_id', False),
        ('fundamental_questions', 'level_number', False),
        ('fundamental_questions', 'question_id', False),
        ('fundamental_sessions', 'class_id', False),
        ('fundamental_sessions', 'teacher_id', False),
        ('fundamental_sessions', 'strand_id', False),
        ('fundamental_sessions', 'is_active', False),
        ('fundamental_pupil_attempts', 'session_id', False),
        ('fundamental_pupil_attempts', 'pupil_id', False),
        ('fundamental_pupil_attempts', 'is_complete', False),
        ('fundamental_responses', 'attempt_id', False),
        ('fundamental_responses', 'question_id', False),
        ('fundamental_responses', 'level_number', False),
    ):
        _ensure_index(table_name, column_name, unique=unique)

    for table_name, column_name, referred_table in (
        ('fundamental_levels', 'strand_id', 'fundamental_strands'),
        ('fundamental_questions', 'strand_id', 'fundamental_strands'),
        ('fundamental_sessions', 'class_id', 'school_classes'),
        ('fundamental_sessions', 'teacher_id', 'users'),
        ('fundamental_sessions', 'strand_id', 'fundamental_strands'),
        ('fundamental_pupil_attempts', 'session_id', 'fundamental_sessions'),
        ('fundamental_pupil_attempts', 'pupil_id', 'pupils'),
        ('fundamental_responses', 'attempt_id', 'fundamental_pupil_attempts'),
        ('fundamental_responses', 'question_id', 'fundamental_questions'),
    ):
        _ensure_foreign_key(
            table_name,
            column_name,
            referred_table,
            name=f'fk_{table_name}_{column_name}',
        )


def downgrade():
    # These tables may predate Alembic and contain production assessment data.
    # This adoption migration is deliberately irreversible and non-destructive.
    pass
