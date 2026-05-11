"""Scope school class names by school.

Revision ID: 20260511_01
Revises: 20260508_01
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = '20260511_01'
down_revision = '20260508_01'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column['name'] for column in inspector.get_columns(table_name)}


def _drop_unique_constraints_on_name(inspector) -> None:
    for constraint in inspector.get_unique_constraints('school_classes'):
        cols = constraint.get('column_names') or []
        name = constraint.get('name')
        if cols == ['name'] and name:
            op.drop_constraint(name, 'school_classes', type_='unique')


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_column(inspector, 'school_classes', 'school_id'):
        op.add_column('school_classes', sa.Column('school_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_school_classes_school_id_schools', 'school_classes', 'schools', ['school_id'], ['id'])
        op.create_index(op.f('ix_school_classes_school_id'), 'school_classes', ['school_id'], unique=False)

    default_school_id = bind.execute(text("SELECT id FROM schools WHERE slug = 'barrow-school' LIMIT 1")).scalar()
    if default_school_id is None:
        default_school_id = bind.execute(text("SELECT id FROM schools ORDER BY id LIMIT 1")).scalar()
    if default_school_id is not None:
        bind.execute(text("UPDATE school_classes SET school_id = :sid WHERE school_id IS NULL"), {'sid': default_school_id})

    inspector = inspect(bind)
    _drop_unique_constraints_on_name(inspector)

    inspector = inspect(bind)
    unique_names = {c.get('name') for c in inspector.get_unique_constraints('school_classes')}
    if 'uq_school_class_name_per_school' not in unique_names:
        op.create_unique_constraint('uq_school_class_name_per_school', 'school_classes', ['school_id', 'name'])

    op.execute("ALTER TABLE school_classes ALTER COLUMN school_id SET NOT NULL")


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    unique_names = {c.get('name') for c in inspector.get_unique_constraints('school_classes')}
    if 'uq_school_class_name_per_school' in unique_names:
        op.drop_constraint('uq_school_class_name_per_school', 'school_classes', type_='unique')
    op.create_unique_constraint('school_classes_name_key', 'school_classes', ['name'])
