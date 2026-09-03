"""Explicitly restore Barrow School's pre-rollover working year.

Revision ID: 20260903_01
Revises: 20260901_01
"""
from alembic import op
import sqlalchemy as sa


revision = '20260903_01'
down_revision = '20260901_01'
branch_labels = None
depends_on = None

SCHOOL_SLUG = 'barrow-school'
SOURCE_YEAR = '2025/26'
INCORRECT_YEAR = '2026/27'


def rewind_barrow_school(bind) -> int:
    """Apply the explicitly requested working-year correction to Barrow only."""
    academic_years = sa.table(
        'academic_years',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
    )
    schools = sa.table(
        'schools',
        sa.column('slug', sa.String),
        sa.column('current_academic_year_id', sa.Integer),
    )

    source_year_id = bind.execute(
        sa.select(academic_years.c.id).where(academic_years.c.name == SOURCE_YEAR)
    ).scalar_one_or_none()
    incorrect_year_id = bind.execute(
        sa.select(academic_years.c.id).where(academic_years.c.name == INCORRECT_YEAR)
    ).scalar_one_or_none()
    if source_year_id is None or incorrect_year_id is None:
        return 0

    result = bind.execute(
        schools.update()
        .where(
            schools.c.slug == SCHOOL_SLUG,
            schools.c.current_academic_year_id == incorrect_year_id,
        )
        .values(current_academic_year_id=source_year_id)
    )
    return result.rowcount or 0


def upgrade():
    rewind_barrow_school(op.get_bind())


def downgrade():
    # Do not advance the school again without an administrator confirming it.
    pass
