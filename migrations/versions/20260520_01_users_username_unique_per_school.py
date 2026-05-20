"""users username unique per school

Revision ID: 20260520_01
Revises: 20260514_01
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260520_01'
down_revision = '20260514_01'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for index in inspector.get_indexes('users'):
        if index.get('unique') and index.get('column_names') == ['username']:
            op.drop_index(index['name'], table_name='users')

    for constraint in inspector.get_unique_constraints('users'):
        cols = constraint.get('column_names') or []
        if cols == ['username']:
            op.drop_constraint(constraint['name'], 'users', type_='unique')

    op.create_index(
        'uq_users_school_id_username_lower',
        'users',
        ['school_id', sa.text('lower(username)')],
        unique=True,
    )


def downgrade():
    op.drop_index('uq_users_school_id_username_lower', table_name='users')
    op.create_unique_constraint('uq_users_username', 'users', ['username'])
