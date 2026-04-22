"""Add user force-password-change flag.

Revision ID: 20260422_01
Revises: 20260417_01
Create Date: 2026-04-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260422_01'
down_revision = '20260417_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('require_password_change', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('users', 'require_password_change')
