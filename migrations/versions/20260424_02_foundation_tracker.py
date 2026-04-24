"""Add foundation tracker results table.

Revision ID: 20260424_02
Revises: 20260424_01
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = '20260424_02'
down_revision = '20260424_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'foundation_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pupil_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=20), nullable=False),
        sa.Column('half_term', sa.String(length=20), nullable=False),
        sa.Column('subject', sa.String(length=20), nullable=False),
        sa.Column('judgement', sa.String(length=50), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pupil_id'], ['pupils.id'], ),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pupil_id', 'academic_year', 'half_term', 'subject', name='uq_foundation_result_scope'),
    )
    op.create_index(op.f('ix_foundation_results_academic_year'), 'foundation_results', ['academic_year'], unique=False)
    op.create_index(op.f('ix_foundation_results_half_term'), 'foundation_results', ['half_term'], unique=False)
    op.create_index(op.f('ix_foundation_results_pupil_id'), 'foundation_results', ['pupil_id'], unique=False)
    op.create_index(op.f('ix_foundation_results_subject'), 'foundation_results', ['subject'], unique=False)
    op.create_index(op.f('ix_foundation_results_updated_by_user_id'), 'foundation_results', ['updated_by_user_id'], unique=False)
    op.create_index('ix_foundation_results_lookup', 'foundation_results', ['academic_year', 'half_term', 'subject'], unique=False)


def downgrade():
    op.drop_index('ix_foundation_results_lookup', table_name='foundation_results')
    op.drop_index(op.f('ix_foundation_results_updated_by_user_id'), table_name='foundation_results')
    op.drop_index(op.f('ix_foundation_results_subject'), table_name='foundation_results')
    op.drop_index(op.f('ix_foundation_results_pupil_id'), table_name='foundation_results')
    op.drop_index(op.f('ix_foundation_results_half_term'), table_name='foundation_results')
    op.drop_index(op.f('ix_foundation_results_academic_year'), table_name='foundation_results')
    op.drop_table('foundation_results')
