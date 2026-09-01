"""Rewind working years incorrectly advanced by the initial backfill.

Revision ID: 20260901_01
Revises: 20260824_01
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = '20260901_01'
down_revision = '20260824_01'
branch_labels = None
depends_on = None

SOURCE_YEAR = '2025/26'
INCORRECT_YEAR = '2026/27'


def rewind_unpromoted_schools(bind) -> int:
    """Restore the pre-September working year when no promotion was recorded."""
    academic_years = sa.table(
        'academic_years',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('is_current', sa.Boolean),
        sa.column('is_archived', sa.Boolean),
        sa.column('created_at', sa.DateTime),
    )
    schools = sa.table(
        'schools',
        sa.column('id', sa.Integer),
        sa.column('current_academic_year_id', sa.Integer),
    )
    history = sa.table(
        'pupil_class_history',
        sa.column('school_id', sa.Integer),
        sa.column('academic_year', sa.String),
        sa.column('promoted_to_year_group', sa.Integer),
    )

    source_year_id = bind.execute(
        sa.select(academic_years.c.id).where(academic_years.c.name == SOURCE_YEAR)
    ).scalar_one_or_none()
    if source_year_id is None:
        result = bind.execute(
            academic_years.insert().values(
                name=SOURCE_YEAR,
                is_current=False,
                is_archived=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        source_year_id = result.inserted_primary_key[0]

    incorrect_year_id = bind.execute(
        sa.select(academic_years.c.id).where(academic_years.c.name == INCORRECT_YEAR)
    ).scalar_one_or_none()
    if incorrect_year_id is None:
        return 0

    promoted_schools = sa.select(history.c.school_id).where(
        history.c.school_id.is_not(None),
        history.c.academic_year == SOURCE_YEAR,
        history.c.promoted_to_year_group.is_not(None),
    )
    result = bind.execute(
        schools.update()
        .where(
            schools.c.current_academic_year_id == incorrect_year_id,
            schools.c.id.not_in(promoted_schools),
        )
        .values(current_academic_year_id=source_year_id)
    )
    return result.rowcount or 0


def upgrade():
    rewind_unpromoted_schools(op.get_bind())


def downgrade():
    # Deliberately irreversible: advancing these schools again without an admin's
    # confirmation would recreate the data error this repair fixes.
    pass
