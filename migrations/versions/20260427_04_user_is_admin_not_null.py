"""Enforce users.is_admin as non-null with default false.

Revision ID: 20260427_04
Revises: 20260427_03
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '20260427_04'
down_revision = '20260427_03'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    if not (_has_table(bind, 'users') and _has_column(bind, 'users', 'is_admin')):
        return

    bind.execute(text('UPDATE users SET is_admin = FALSE WHERE is_admin IS NULL'))

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'is_admin',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text('FALSE'),
        )


def downgrade():
    bind = op.get_bind()
    if not (_has_table(bind, 'users') and _has_column(bind, 'users', 'is_admin')):
        return

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'is_admin',
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
