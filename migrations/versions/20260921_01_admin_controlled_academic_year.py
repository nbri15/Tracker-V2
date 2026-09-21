"""Make school academic years explicit and snapshot Fundamentals sessions.

Revision ID: 20260921_01
Revises: 20260909_03
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = '20260921_01'
down_revision = '20260909_03'
branch_labels = None
depends_on = None

SAFE_FALLBACK_YEAR = '2025/26'


def _ensure_safe_fallback_year(bind) -> int:
    academic_years = sa.table(
        'academic_years',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('is_current', sa.Boolean),
        sa.column('is_archived', sa.Boolean),
        sa.column('created_at', sa.DateTime),
    )
    year_id = bind.execute(
        sa.select(academic_years.c.id).where(academic_years.c.name == SAFE_FALLBACK_YEAR)
    ).scalar_one_or_none()
    if year_id is None:
        bind.execute(academic_years.insert().values(
            name=SAFE_FALLBACK_YEAR,
            is_current=False,
            is_archived=False,
            created_at=datetime.now(timezone.utc),
        ))
        year_id = bind.execute(
            sa.select(academic_years.c.id).where(academic_years.c.name == SAFE_FALLBACK_YEAR)
        ).scalar_one()
    return year_id


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fallback_year_id = _ensure_safe_fallback_year(bind)

    # Preserve every explicit school value. Only legacy NULL rows receive the
    # conservative pre-rollover year; no class or pupil data is touched.
    schools = sa.table(
        'schools',
        sa.column('current_academic_year_id', sa.Integer),
    )
    bind.execute(
        schools.update()
        .where(schools.c.current_academic_year_id.is_(None))
        .values(current_academic_year_id=fallback_year_id)
    )

    school_columns = {column['name'] for column in inspector.get_columns('schools')}
    if 'academic_year_reminder_dismissed_for' not in school_columns:
        with op.batch_alter_table('schools') as batch_op:
            batch_op.add_column(sa.Column('academic_year_reminder_dismissed_for', sa.String(length=20), nullable=True))

    with op.batch_alter_table('schools') as batch_op:
        batch_op.alter_column('current_academic_year_id', existing_type=sa.Integer(), nullable=False)

    session_columns = {column['name'] for column in inspector.get_columns('fundamental_sessions')}
    if 'academic_year' not in session_columns:
        with op.batch_alter_table('fundamental_sessions') as batch_op:
            batch_op.add_column(sa.Column('academic_year', sa.String(length=20), nullable=True))

    # Do not guess the year of historical sessions that pre-date this field.
    # New sessions always snapshot the school's explicit stored year.
    session_indexes = {index['name'] for index in sa.inspect(bind).get_indexes('fundamental_sessions')}
    if 'ix_fundamental_sessions_academic_year' not in session_indexes:
        op.create_index('ix_fundamental_sessions_academic_year', 'fundamental_sessions', ['academic_year'])


def downgrade():
    with op.batch_alter_table('fundamental_sessions') as batch_op:
        batch_op.drop_index('ix_fundamental_sessions_academic_year')
        batch_op.drop_column('academic_year')
    with op.batch_alter_table('schools') as batch_op:
        batch_op.alter_column('current_academic_year_id', existing_type=sa.Integer(), nullable=True)
        batch_op.drop_column('academic_year_reminder_dismissed_for')
