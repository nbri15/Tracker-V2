"""Add simple SATs exam tabs and notes support safely."""
from alembic import op
import sqlalchemy as sa

revision = '20260512_04_simple_sats_tabs_and_notes'
down_revision = '20260512_03_simple_sats_tables_cleanup'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, 'sats_results') and not _has_column(inspector, 'sats_results', 'notes'):
        with op.batch_alter_table('sats_results') as batch_op:
            batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))

    if not _has_table(inspector, 'simple_sats_exam_tabs'):
        op.create_table(
            'simple_sats_exam_tabs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
            sa.Column('academic_year', sa.String(length=20), nullable=False),
            sa.Column('exam_number', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('display_order', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('school_id', 'academic_year', 'exam_number', name='uq_simple_sats_exam_tabs_scope'),
        )


def downgrade():
    pass
