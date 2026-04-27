"""Add legacy users.is_admin compatibility column when missing.

Revision ID: 20260427_03
Revises: 20260427_02
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '20260427_03'
down_revision = '20260427_02'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    if not _has_table(bind, 'users'):
        return

    if not _has_column(bind, 'users', 'is_admin'):
        op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True))

    bind.execute(text("""
        UPDATE users
        SET is_admin = CASE
            WHEN role IN ('school_admin', 'admin', 'executive_admin') THEN TRUE
            ELSE FALSE
        END
        WHERE is_admin IS NULL
    """))


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, 'users') and _has_column(bind, 'users', 'is_admin'):
        op.drop_column('users', 'is_admin')
