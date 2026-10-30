"""School intervention library and non-destructive pupil assignments.

Revision ID: 20261030_01
Revises: 20261021_01
"""
from alembic import op
import sqlalchemy as sa

revision = '20261030_01'
down_revision = '20261021_01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if 'closed_by_teacher' not in {column['name'] for column in inspector.get_columns('interventions')}:
        op.add_column('interventions', sa.Column('closed_by_teacher', sa.Boolean(), nullable=False, server_default=sa.false()))
        interventions = sa.table('interventions', sa.column('is_active', sa.Boolean()), sa.column('closed_by_teacher', sa.Boolean()))
        # An existing closed record stays closed until a teacher explicitly reopens it.
        op.execute(interventions.update().where(interventions.c.is_active.is_(False)).values(closed_by_teacher=True))
    if 'intervention_programmes' not in tables:
        op.create_table('intervention_programmes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('name_key', sa.String(120), nullable=False),
            sa.Column('subject', sa.String(20), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint('school_id', 'subject', 'name_key', name='uq_intervention_programme_name'))
        op.create_index('ix_intervention_programmes_school_id', 'intervention_programmes', ['school_id'])
    if 'intervention_programme_assignments' not in tables:
        op.create_table('intervention_programme_assignments',
            sa.Column('intervention_id', sa.Integer(), sa.ForeignKey('interventions.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('programme_id', sa.Integer(), sa.ForeignKey('intervention_programmes.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False))
        op.create_index('ix_intervention_programme_assignments_school_id', 'intervention_programme_assignments', ['school_id'])


def downgrade():
    raise RuntimeError('Intervention programmes contain pupil support history. Use a reviewed recovery plan rather than dropping these records.')
