"""Schema safety backfill for archive/school scoped columns.

Revision ID: 20260508_01_schema_safety_backfill
Revises: 20260507_01_add_pupil_send
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = '20260508_01_schema_safety_backfill'
down_revision = '20260507_01_add_pupil_send'
branch_labels = None
depends_on = None

def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name) and any(col['name'] == column_name for col in inspector.get_columns(table_name))


def _add_column_if_missing(table_name: str, column_name: str, column_type: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        if not _has_column(bind, table_name, column_name):
            op.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    else:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}")

def upgrade() -> None:
    _add_column_if_missing('pupils', 'send', 'BOOLEAN')
    _add_column_if_missing('pupils', 'join_year_group', 'INTEGER')
    _add_column_if_missing('pupils', 'join_date', 'DATE')
    _add_column_if_missing('pupils', 'is_archived', 'BOOLEAN')
    _add_column_if_missing('pupils', 'archived_at', 'TIMESTAMP')
    _add_column_if_missing('pupils', 'archived_by_user_id', 'INTEGER')
    _add_column_if_missing('pupils', 'archive_reason', 'TEXT')
    op.execute("UPDATE pupils SET send = FALSE WHERE send IS NULL")
    op.execute("UPDATE pupils SET is_archived = FALSE WHERE is_archived IS NULL")

    _add_column_if_missing('schools', 'is_archived', 'BOOLEAN')
    _add_column_if_missing('schools', 'archived_at', 'TIMESTAMP')
    _add_column_if_missing('schools', 'archived_by_user_id', 'INTEGER')
    _add_column_if_missing('schools', 'archive_reason', 'TEXT')
    op.execute("UPDATE schools SET is_archived = FALSE WHERE is_archived IS NULL")

    _add_column_if_missing('phonics_test_columns', 'school_id', 'INTEGER')
    _add_column_if_missing('times_table_test_columns', 'school_id', 'INTEGER')

    id_type = 'INTEGER PRIMARY KEY' if op.get_bind().dialect.name == 'sqlite' else 'SERIAL PRIMARY KEY'
    created_default = 'CURRENT_TIMESTAMP' if op.get_bind().dialect.name == 'sqlite' else 'NOW()'
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id {id_type},
            user_id INTEGER NOT NULL,
            school_id INTEGER NULL,
            action VARCHAR(120) NOT NULL,
            target_type VARCHAR(80) NOT NULL,
            target_id INTEGER NOT NULL,
            details TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {created_default}
        )
        """
    )


def downgrade() -> None:
    # Intentionally no destructive downgrade for safety.
    pass
