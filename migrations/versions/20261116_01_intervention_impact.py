"""Remember when support began and the starting score, so impact can be measured.

Adds four optional columns. No existing record is changed or deleted.

Revision ID: 20261116_01
Revises: 20261030_01
"""
from alembic import op
import sqlalchemy as sa

revision = '20261116_01'
down_revision = '20261030_01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {column['name'] for column in inspector.get_columns('interventions')}
    for name, column_type in [('started_on', sa.Date()), ('ended_on', sa.Date()),
                              ('baseline_percent', sa.Float()), ('baseline_band', sa.String(40))]:
        if name not in existing:
            op.add_column('interventions', sa.Column(name, column_type, nullable=True))


def downgrade():
    raise RuntimeError('Intervention baselines are support history. Use a reviewed recovery plan rather than dropping them.')
