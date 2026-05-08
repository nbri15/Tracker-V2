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


def upgrade() -> None:
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS send BOOLEAN")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS join_year_group INTEGER")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS join_date DATE")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS is_archived BOOLEAN")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS archived_by_user_id INTEGER")
    op.execute("ALTER TABLE pupils ADD COLUMN IF NOT EXISTS archive_reason TEXT")
    op.execute("UPDATE pupils SET send = FALSE WHERE send IS NULL")
    op.execute("UPDATE pupils SET is_archived = FALSE WHERE is_archived IS NULL")

    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS is_archived BOOLEAN")
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP")
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS archived_by_user_id INTEGER")
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS archive_reason TEXT")
    op.execute("UPDATE schools SET is_archived = FALSE WHERE is_archived IS NULL")

    op.execute("ALTER TABLE phonics_test_columns ADD COLUMN IF NOT EXISTS school_id INTEGER")
    op.execute("ALTER TABLE times_table_test_columns ADD COLUMN IF NOT EXISTS school_id INTEGER")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            school_id INTEGER NULL,
            action VARCHAR(120) NOT NULL,
            target_type VARCHAR(80) NOT NULL,
            target_id INTEGER NOT NULL,
            details TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    # Intentionally no destructive downgrade for safety.
    pass
