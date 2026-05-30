"""Add dashboard and import performance indexes.

Revision ID: 20260530_01
Revises: 20260520_02
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa


revision = '20260530_01'
down_revision = '20260520_02'
branch_labels = None
depends_on = None


INDEXES = (
    ('ix_pupils_dashboard_scope', 'pupils', ['school_id', 'is_demo', 'is_active', 'class_id']),
    ('ix_subject_results_school_year_pupil', 'subject_results', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_writing_results_school_year_pupil', 'writing_results', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_foundation_results_school_year_pupil', 'foundation_results', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_reception_entries_school_year_pupil', 'reception_tracker_entries', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_sats_column_results_school_year_pupil', 'sats_column_results', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_sats_results_school_year_pupil', 'sats_results', ['school_id', 'academic_year', 'pupil_id']),
    ('ix_sats_writing_school_year_pupil', 'sats_writing_results', ['school_id', 'academic_year', 'pupil_id']),
)


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index.get('name') for index in inspector.get_indexes(table_name)}


def upgrade():
    for name, table_name, columns in INDEXES:
        if name not in _existing_indexes(table_name):
            op.create_index(name, table_name, columns)


def downgrade():
    for name, table_name, _columns in reversed(INDEXES):
        if name in _existing_indexes(table_name):
            op.drop_index(name, table_name=table_name)
