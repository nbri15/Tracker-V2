"""Year-scoped assessment setup and result snapshots; preserve all legacy data.

Revision ID: 20261005_01
Revises: 20260922_01
"""
from alembic import op
import sqlalchemy as sa

revision = '20261005_01'
down_revision = '20260922_01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('assessment_configurations'):
        op.create_table('assessment_configurations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
            sa.Column('academic_year', sa.String(20), nullable=False),
            sa.Column('year_group', sa.Integer(), nullable=False),
            sa.Column('subject', sa.String(20), nullable=False),
            sa.Column('term', sa.String(20), nullable=False),
            sa.Column('paper_1_name', sa.String(100), nullable=False),
            sa.Column('paper_1_max', sa.Integer(), nullable=False),
            sa.Column('paper_2_name', sa.String(100), nullable=False),
            sa.Column('paper_2_max', sa.Integer(), nullable=False),
            sa.Column('combined_max', sa.Integer(), nullable=False),
            sa.Column('below_are_threshold_percent', sa.Float(), nullable=False),
            sa.Column('on_track_threshold_percent', sa.Float(), nullable=False),
            sa.Column('exceeding_threshold_percent', sa.Float(), nullable=False),
            sa.UniqueConstraint('school_id', 'academic_year', 'year_group', 'subject', 'term', name='uq_assessment_configuration_scope'))
        op.create_index('ix_assessment_configurations_school_id', 'assessment_configurations', ['school_id'])
    if not inspector.has_table('assessment_reviews'):
        op.create_table('assessment_reviews',
            sa.Column('id', sa.String(64), primary_key=True),
            sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('kind', sa.String(30), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=False),
            sa.Column('report', sa.JSON(), nullable=False),
            sa.Column('baseline', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('confirmed_at', sa.DateTime(), nullable=True))
        op.create_index('ix_assessment_reviews_school_id', 'assessment_reviews', ['school_id'])
    existing = {column['name'] for column in inspector.get_columns('subject_results')}
    if 'configuration_snapshot' not in existing:
        op.add_column('subject_results', sa.Column('configuration_snapshot', sa.JSON(), nullable=True))
    if 'cohort_year_group' not in existing:
        op.add_column('subject_results', sa.Column('cohort_year_group', sa.Integer(), nullable=True))
    constraints = {item['name'] for item in inspector.get_unique_constraints('gap_templates')}
    if 'uq_gap_template_scope' in constraints and 'uq_gap_template_school_scope' not in constraints:
        with op.batch_alter_table('gap_templates') as batch:
            batch.drop_constraint('uq_gap_template_scope', type_='unique')
            batch.create_unique_constraint('uq_gap_template_school_scope', ['school_id', 'year_group', 'subject', 'term', 'academic_year'])
    # No backfill/recalculation: the original thresholds cannot be reconstructed
    # reliably for old results. Their saved outcomes remain authoritative.


def downgrade():
    raise RuntimeError('This revision preserves assessment history. Restore application code without dropping review/configuration/snapshot data; schema downgrade requires a reviewed backup plan.')
