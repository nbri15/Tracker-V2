"""Add archive metadata and audit log for GDPR-safe deletion workflows.

Revision ID: 20260428_01
Revises: 20260427_05
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = '20260428_01'
down_revision = '20260427_05'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pupils', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('pupils', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.add_column('pupils', sa.Column('archived_by_user_id', sa.Integer(), nullable=True))
    op.add_column('pupils', sa.Column('archive_reason', sa.Text(), nullable=True))
    op.create_index('ix_pupils_is_archived', 'pupils', ['is_archived'], unique=False)
    op.create_index('ix_pupils_archived_by_user_id', 'pupils', ['archived_by_user_id'], unique=False)
    op.create_foreign_key('fk_pupils_archived_by_user_id', 'pupils', 'users', ['archived_by_user_id'], ['id'])

    op.add_column('schools', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('schools', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.add_column('schools', sa.Column('archived_by_user_id', sa.Integer(), nullable=True))
    op.add_column('schools', sa.Column('archive_reason', sa.Text(), nullable=True))
    op.create_index('ix_schools_is_archived', 'schools', ['is_archived'], unique=False)
    op.create_index('ix_schools_archived_by_user_id', 'schools', ['archived_by_user_id'], unique=False)
    op.create_foreign_key('fk_schools_archived_by_user_id', 'schools', 'users', ['archived_by_user_id'], ['id'])

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=120), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_school_id', 'audit_logs', ['school_id'], unique=False)
    op.create_index('ix_audit_logs_target_id', 'audit_logs', ['target_id'], unique=False)
    op.create_index('ix_audit_logs_target_type', 'audit_logs', ['target_type'], unique=False)
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)


def downgrade():
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_target_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_target_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_school_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_constraint('fk_schools_archived_by_user_id', 'schools', type_='foreignkey')
    op.drop_index('ix_schools_archived_by_user_id', table_name='schools')
    op.drop_index('ix_schools_is_archived', table_name='schools')
    op.drop_column('schools', 'archive_reason')
    op.drop_column('schools', 'archived_by_user_id')
    op.drop_column('schools', 'archived_at')
    op.drop_column('schools', 'is_archived')

    op.drop_constraint('fk_pupils_archived_by_user_id', 'pupils', type_='foreignkey')
    op.drop_index('ix_pupils_archived_by_user_id', table_name='pupils')
    op.drop_index('ix_pupils_is_archived', table_name='pupils')
    op.drop_column('pupils', 'archive_reason')
    op.drop_column('pupils', 'archived_by_user_id')
    op.drop_column('pupils', 'archived_at')
    op.drop_column('pupils', 'is_archived')
