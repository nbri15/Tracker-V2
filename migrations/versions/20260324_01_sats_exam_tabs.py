"""Add SATs exam tabs and tab-scoped columns.

Revision ID: 20260324_01
Revises: 20260323_01
Create Date: 2026-03-24 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


revision = '20260324_01'
down_revision = '20260323_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sats_exam_tabs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_group', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sats_exam_tabs_year_group', 'sats_exam_tabs', ['year_group'])
    op.create_index('ix_sats_exam_tabs_year_order', 'sats_exam_tabs', ['year_group', 'display_order'])

    op.add_column('sats_column_settings', sa.Column('exam_tab_id', sa.Integer(), nullable=True))
    op.add_column('sats_column_settings', sa.Column('score_type', sa.String(length=20), nullable=False, server_default='paper'))
    op.add_column('sats_column_settings', sa.Column('column_key', sa.String(length=60), nullable=True))
    op.create_index('ix_sats_column_settings_exam_tab_id', 'sats_column_settings', ['exam_tab_id'])

    bind = op.get_bind()
    now_utc = datetime.now(timezone.utc)
    bind.execute(sa.text(
        """
        INSERT INTO sats_exam_tabs (year_group, name, display_order, is_active, created_at, updated_at)
        VALUES (6, 'Legacy SATs', 1, 1, :now_utc, :now_utc)
        """
    ), {'now_utc': now_utc})
    legacy_tab_id = bind.scalar(sa.text("SELECT id FROM sats_exam_tabs WHERE year_group = 6 ORDER BY id LIMIT 1"))
    bind.execute(sa.text("UPDATE sats_column_settings SET exam_tab_id = :tab_id WHERE exam_tab_id IS NULL"), {'tab_id': legacy_tab_id})

    with op.batch_alter_table('sats_column_settings', schema=None) as batch_op:
        batch_op.alter_column('exam_tab_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_sats_column_settings_exam_tab', 'sats_exam_tabs', ['exam_tab_id'], ['id'])


def downgrade():
    with op.batch_alter_table('sats_column_settings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sats_column_settings_exam_tab', type_='foreignkey')
    op.drop_index('ix_sats_column_settings_exam_tab_id', table_name='sats_column_settings')
    op.drop_column('sats_column_settings', 'column_key')
    op.drop_column('sats_column_settings', 'score_type')
    op.drop_column('sats_column_settings', 'exam_tab_id')

    op.drop_index('ix_sats_exam_tabs_year_order', table_name='sats_exam_tabs')
    op.drop_index('ix_sats_exam_tabs_year_group', table_name='sats_exam_tabs')
    op.drop_table('sats_exam_tabs')
