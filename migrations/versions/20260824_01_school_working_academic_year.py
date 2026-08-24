"""Add school-scoped working academic year.

Revision ID: 20260824_01
Revises: 20260530_01
"""
from alembic import op
import sqlalchemy as sa


revision = '20260824_01'
down_revision = '20260530_01'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('schools') as batch_op:
        batch_op.add_column(sa.Column('current_academic_year_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_schools_current_academic_year_id', ['current_academic_year_id'])
        batch_op.create_foreign_key(
            'fk_schools_current_academic_year_id',
            'academic_years',
            ['current_academic_year_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('schools') as batch_op:
        batch_op.drop_constraint('fk_schools_current_academic_year_id', type_='foreignkey')
        batch_op.drop_index('ix_schools_current_academic_year_id')
        batch_op.drop_column('current_academic_year_id')
