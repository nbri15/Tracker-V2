"""Add demo-scope flags to core models.

Revision ID: 20260427_01
Revises: 20260424_02
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = '20260427_01'
down_revision = '20260424_02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('school_classes', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('pupils', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('interventions', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_index(op.f('ix_users_is_demo'), 'users', ['is_demo'], unique=False)
    op.create_index(op.f('ix_school_classes_is_demo'), 'school_classes', ['is_demo'], unique=False)
    op.create_index(op.f('ix_pupils_is_demo'), 'pupils', ['is_demo'], unique=False)
    op.create_index(op.f('ix_interventions_is_demo'), 'interventions', ['is_demo'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_interventions_is_demo'), table_name='interventions')
    op.drop_index(op.f('ix_pupils_is_demo'), table_name='pupils')
    op.drop_index(op.f('ix_school_classes_is_demo'), table_name='school_classes')
    op.drop_index(op.f('ix_users_is_demo'), table_name='users')

    op.drop_column('interventions', 'is_demo')
    op.drop_column('pupils', 'is_demo')
    op.drop_column('school_classes', 'is_demo')
    op.drop_column('users', 'is_demo')
