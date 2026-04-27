"""Add schools tenancy, role migration, and school_id backfill.

Revision ID: 20260427_02
Revises: 20260427_01
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '20260427_02'
down_revision = '20260427_01'
branch_labels = None
depends_on = None


SCHOOL_ID_TABLES = [
    'users',
    'school_classes',
    'pupils',
    'academic_years',
    'assessment_settings',
    'subject_results',
    'writing_results',
    'gap_templates',
    'gap_questions',
    'gap_scores',
    'interventions',
    'reception_tracker_entries',
    'phonics_test_columns',
    'phonics_scores',
    'times_table_test_columns',
    'times_table_scores',
    'foundation_results',
    'tracker_mode_settings',
    'sats_exam_tabs',
    'sats_column_settings',
    'sats_column_results',
    'sats_results',
    'sats_writing_results',
    'pupil_class_history',
]


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()

    if not _has_table(bind, 'schools'):
        op.create_table(
            'schools',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=140), nullable=False),
            sa.Column('slug', sa.String(length=140), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('name'),
            sa.UniqueConstraint('slug'),
        )
        op.create_index(op.f('ix_schools_slug'), 'schools', ['slug'], unique=True)
        op.create_index(op.f('ix_schools_is_demo'), 'schools', ['is_demo'], unique=False)

    for table_name in SCHOOL_ID_TABLES:
        if _has_table(bind, table_name) and not _has_column(bind, table_name, 'school_id'):
            op.add_column(table_name, sa.Column('school_id', sa.Integer(), nullable=True))
            op.create_index(f'ix_{table_name}_school_id', table_name, ['school_id'], unique=False)
            op.create_foreign_key(f'fk_{table_name}_school_id', table_name, 'schools', ['school_id'], ['id'])

    if _has_table(bind, 'users') and _has_column(bind, 'users', 'role'):
        bind.execute(text("UPDATE users SET role = 'school_admin' WHERE role = 'admin'"))

    barrow_id = bind.execute(text("SELECT id FROM schools WHERE slug='barrow-school' LIMIT 1")).scalar()
    if not barrow_id:
        bind.execute(text("INSERT INTO schools (name, slug, is_active, is_demo) VALUES ('Barrow School', 'barrow-school', TRUE, FALSE)"))
        barrow_id = bind.execute(text("SELECT id FROM schools WHERE slug='barrow-school' LIMIT 1")).scalar()

    demo_id = bind.execute(text("SELECT id FROM schools WHERE slug='demo-school' LIMIT 1")).scalar()
    if not demo_id:
        bind.execute(text("INSERT INTO schools (name, slug, is_active, is_demo) VALUES ('Demo School', 'demo-school', TRUE, TRUE)"))
        demo_id = bind.execute(text("SELECT id FROM schools WHERE slug='demo-school' LIMIT 1")).scalar()

    for table_name in SCHOOL_ID_TABLES:
        if not (_has_table(bind, table_name) and _has_column(bind, table_name, 'school_id')):
            continue
        if _has_column(bind, table_name, 'is_demo'):
            bind.execute(text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND is_demo = TRUE"), {'demo_id': demo_id})
            bind.execute(text(f"UPDATE {table_name} SET school_id = :barrow_id WHERE school_id IS NULL AND (is_demo = FALSE OR is_demo IS NULL)"), {'barrow_id': barrow_id})
        else:
            bind.execute(text(f"UPDATE {table_name} SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})


def downgrade():
    bind = op.get_bind()
    for table_name in reversed(SCHOOL_ID_TABLES):
        if _has_table(bind, table_name) and _has_column(bind, table_name, 'school_id'):
            op.drop_constraint(f'fk_{table_name}_school_id', table_name, type_='foreignkey')
            op.drop_index(f'ix_{table_name}_school_id', table_name=table_name)
            op.drop_column(table_name, 'school_id')

    if _has_table(bind, 'schools'):
        op.drop_index(op.f('ix_schools_is_demo'), table_name='schools')
        op.drop_index(op.f('ix_schools_slug'), table_name='schools')
        op.drop_table('schools')
