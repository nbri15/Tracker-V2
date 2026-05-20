"""Scope pupil class history uniqueness to school.

Revision ID: 20260520_02
Revises: 20260520_01
Create Date: 2026-05-20
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260520_02'
down_revision = '20260520_01'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('uq_pupil_class_history_scope', 'pupil_class_history', type_='unique')
    op.create_unique_constraint(
        'uq_pupil_class_history_school_scope',
        'pupil_class_history',
        ['school_id', 'pupil_id', 'academic_year'],
    )


def downgrade():
    op.drop_constraint('uq_pupil_class_history_school_scope', 'pupil_class_history', type_='unique')
    op.create_unique_constraint(
        'uq_pupil_class_history_scope',
        'pupil_class_history',
        ['pupil_id', 'academic_year'],
    )
