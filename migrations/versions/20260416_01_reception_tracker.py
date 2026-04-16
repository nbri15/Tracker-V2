"""Add reception EYFS tracker entries.

Revision ID: 20260416_01
Revises: 20260324_01
Create Date: 2026-04-16 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260416_01'
down_revision = '20260324_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reception_tracker_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('tracking_point', sa.String(length=40), nullable=False),
        sa.Column('area_key', sa.String(length=60), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='not_on_track'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'tracking_point', 'area_key', name='uq_reception_tracker_entry_scope'),
    )
    op.create_index('ix_reception_tracker_entries_pupil_id', 'reception_tracker_entries', ['pupil_id'])
    op.create_index('ix_reception_tracker_entries_academic_year', 'reception_tracker_entries', ['academic_year'])
    op.create_index('ix_reception_tracker_entries_tracking_point', 'reception_tracker_entries', ['tracking_point'])
    op.create_index('ix_reception_tracker_entries_area_key', 'reception_tracker_entries', ['area_key'])

    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO school_classes (name, year_group, teacher_id, is_active)
        SELECT 'Reception', 0, NULL, 1
        WHERE NOT EXISTS (SELECT 1 FROM school_classes WHERE name = 'Reception')
    """))


def downgrade():
    op.drop_index('ix_reception_tracker_entries_area_key', table_name='reception_tracker_entries')
    op.drop_index('ix_reception_tracker_entries_tracking_point', table_name='reception_tracker_entries')
    op.drop_index('ix_reception_tracker_entries_academic_year', table_name='reception_tracker_entries')
    op.drop_index('ix_reception_tracker_entries_pupil_id', table_name='reception_tracker_entries')
    op.drop_table('reception_tracker_entries')
