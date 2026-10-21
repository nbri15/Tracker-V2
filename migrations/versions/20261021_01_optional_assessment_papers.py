"""Allow either assessment paper to be switched off without deleting marks.

Revision ID: 20261021_01
Revises: 20261005_01
"""
from alembic import op
import sqlalchemy as sa

revision = '20261021_01'
down_revision = '20261005_01'
branch_labels = None
depends_on = None


def upgrade():
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('assessment_configurations')}
    for paper in (1, 2):
        name = f'paper_{paper}_enabled'
        if name not in existing:
            op.add_column('assessment_configurations', sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true()))
    # Existing configurations keep both papers enabled. No result is rewritten.


def downgrade():
    raise RuntimeError('Optional-paper settings preserve assessment meaning. Use a reviewed backup plan rather than dropping them.')
