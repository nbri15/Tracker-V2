"""Create simple sats tables and clear legacy SATs data."""
from alembic import op
import sqlalchemy as sa

revision='20260512_03_simple_sats_tables_cleanup'
down_revision='20260512_02_reset_sats_tracker'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('simple_sats_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('pupil_id', sa.Integer(), sa.ForeignKey('pupils.id'), nullable=False),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('exam_number', sa.Integer(), nullable=False),
        sa.Column('arithmetic_score', sa.Integer()), sa.Column('reasoning_1_score', sa.Integer()), sa.Column('reasoning_2_score', sa.Integer()),
        sa.Column('maths_combined_score', sa.Integer()), sa.Column('maths_scaled_score', sa.Integer()),
        sa.Column('reading_score', sa.Integer()), sa.Column('reading_scaled_score', sa.Integer()),
        sa.Column('spelling_score', sa.Integer()), sa.Column('grammar_score', sa.Integer()),
        sa.Column('spag_combined_score', sa.Integer()), sa.Column('spag_scaled_score', sa.Integer()),
        sa.Column('notes', sa.Text()), sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('school_id','pupil_id','academic_year','exam_number', name='uq_simple_sats_results_scope')
    )
    op.create_table('simple_sats_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('academic_year', sa.String(20), nullable=False),
        sa.Column('exam_number', sa.Integer(), nullable=False),
        sa.Column('arithmetic_max', sa.Integer(), nullable=False, server_default='40'),
        sa.Column('reasoning_1_max', sa.Integer(), nullable=False, server_default='35'),
        sa.Column('reasoning_2_max', sa.Integer(), nullable=False, server_default='35'),
        sa.Column('reading_max', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('spelling_max', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('grammar_max', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('school_id','academic_year','exam_number', name='uq_simple_sats_settings_scope')
    )
    conn=op.get_bind()
    for t in ['sats_results','sats_column_results','sats_column_settings','sats_exam_tabs','sats_writing_results']:
        conn.execute(sa.text(f'DELETE FROM {t}'))
    conn.execute(sa.text("DELETE FROM tracker_mode_settings WHERE year_group = 6"))

def downgrade():
    op.drop_table('simple_sats_settings')
    op.drop_table('simple_sats_results')
