"""Ensure school_id exists on all school-scoped tables for stabilisation.

Revision ID: 20260427_05
Revises: 20260427_04
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = '20260427_05'
down_revision = '20260427_04'
branch_labels = None
depends_on = None


REQUIRED_TABLES = [
    'school_classes',
    'pupils',
    'subject_results',
    'writing_results',
    'interventions',
    'foundation_results',
    'phonics_scores',
    'times_table_scores',
    'reception_tracker_entries',
    'sats_exam_tabs',
    'sats_column_results',
    'sats_column_settings',
    'sats_results',
    'sats_writing_results',
    'tracker_mode_settings',
    'assessment_settings',
    'pupil_class_history',
]


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx.get('name') == index_name for idx in inspector.get_indexes(table_name))


def _has_fk(bind, table_name: str, fk_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(fk.get('name') == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade():
    bind = op.get_bind()

    for table_name in REQUIRED_TABLES:
        if not _has_table(bind, table_name):
            continue

        if not _has_column(bind, table_name, 'school_id'):
            op.add_column(table_name, sa.Column('school_id', sa.Integer(), nullable=True))

        index_name = f'ix_{table_name}_school_id'
        if not _has_index(bind, table_name, index_name):
            op.create_index(index_name, table_name, ['school_id'], unique=False)

        fk_name = f'fk_{table_name}_school_id'
        if not _has_fk(bind, table_name, fk_name):
            op.create_foreign_key(fk_name, table_name, 'schools', ['school_id'], ['id'])


def downgrade():
    bind = op.get_bind()

    for table_name in reversed(REQUIRED_TABLES):
        if not _has_table(bind, table_name):
            continue

        fk_name = f'fk_{table_name}_school_id'
        if _has_fk(bind, table_name, fk_name):
            op.drop_constraint(fk_name, table_name, type_='foreignkey')

        index_name = f'ix_{table_name}_school_id'
        if _has_index(bind, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

        if _has_column(bind, table_name, 'school_id'):
            op.drop_column(table_name, 'school_id')
