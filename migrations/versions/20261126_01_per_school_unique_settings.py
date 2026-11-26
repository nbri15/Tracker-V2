"""Make settings and test-column uniqueness per school instead of across all schools.

Before this, only one school in the whole database could have (for example) a Year 6
tracker-mode row, so creating a second school failed part-way. Each rule now includes
school_id. This only widens what is allowed, so existing rows can never break it.

Revision ID: 20261126_01
Revises: 20261116_01
Create Date: 2026-11-26
"""

from alembic import op
import sqlalchemy as sa


revision = '20261126_01'
down_revision = '20261116_01'
branch_labels = None
depends_on = None


# table: (old name, old columns, new name, new columns)
CHANGES = {
    'tracker_mode_settings': (
        'uq_tracker_mode_year_group', ['year_group'],
        'uq_tracker_mode_school_year_group', ['school_id', 'year_group'],
    ),
    'assessment_settings': (
        'uq_assessment_setting_scope', ['year_group', 'subject', 'term'],
        'uq_assessment_setting_school_scope', ['school_id', 'year_group', 'subject', 'term'],
    ),
    'phonics_test_columns': (
        'uq_phonics_test_column_name', ['year_group', 'name'],
        'uq_phonics_test_column_school_name', ['school_id', 'year_group', 'name'],
    ),
    'times_table_test_columns': (
        'uq_times_table_test_column_name', ['year_group', 'name'],
        'uq_times_table_test_column_school_name', ['school_id', 'year_group', 'name'],
    ),
}


def _unique_names(bind, table_name):
    inspector = sa.inspect(bind)
    names = {item['name'] for item in inspector.get_unique_constraints(table_name) if item.get('name')}
    names |= {item['name'] for item in inspector.get_indexes(table_name) if item.get('unique') and item.get('name')}
    return names


def _swap(bind, table_name, drop_name, add_name, add_columns):
    if not sa.inspect(bind).has_table(table_name):
        return
    existing = _unique_names(bind, table_name)
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table(table_name, recreate='always') as batch_op:
            if drop_name in existing:
                batch_op.drop_constraint(drop_name, type_='unique')
            if add_name not in existing:
                batch_op.create_unique_constraint(add_name, add_columns)
        return
    if drop_name in existing:
        # Could be a constraint or a plain unique index depending on how the table was created.
        constraint_names = {item['name'] for item in sa.inspect(bind).get_unique_constraints(table_name)}
        if drop_name in constraint_names:
            op.drop_constraint(drop_name, table_name, type_='unique')
        else:
            op.drop_index(drop_name, table_name=table_name)
    if add_name not in existing:
        op.create_unique_constraint(add_name, table_name, add_columns)


def upgrade():
    bind = op.get_bind()
    for table_name, (old_name, _old_cols, new_name, new_cols) in CHANGES.items():
        _swap(bind, table_name, old_name, new_name, new_cols)


def downgrade():
    # Going back would fail if two schools now share a value, which is exactly the case
    # this migration exists to allow. Refuse rather than half-undo.
    raise RuntimeError('This migration cannot be reversed safely once more than one school has settings.')
