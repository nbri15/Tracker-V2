"""Harden school scoping, backfill school IDs, and enforce users.is_admin defaults.

Revision ID: 20260427_04
Revises: 20260427_03
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '20260427_04'
down_revision = '20260427_03'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col['name'] == column_name for col in inspector.get_columns(table_name))


def _ensure_school_ids_on_settings(bind) -> None:
    for table_name in ('assessment_settings', 'tracker_mode_settings'):
        if not _has_table(bind, table_name):
            continue
        if not _has_column(bind, table_name, 'school_id'):
            op.add_column(table_name, sa.Column('school_id', sa.Integer(), nullable=True))
            op.create_index(f'ix_{table_name}_school_id', table_name, ['school_id'], unique=False)
            op.create_foreign_key(f'fk_{table_name}_school_id', table_name, 'schools', ['school_id'], ['id'])


def _force_school_backfill(bind, demo_id: int, barrow_id: int) -> None:
    bind.execute(text("UPDATE users SET school_id = :demo_id WHERE lower(username) IN ('demo_admin', 'demo_teacher')"), {'demo_id': demo_id})
    bind.execute(text("UPDATE users SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})

    bind.execute(text("UPDATE school_classes SET school_id = :demo_id WHERE is_demo = TRUE OR name LIKE 'Demo %'"), {'demo_id': demo_id})
    bind.execute(text("UPDATE school_classes SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})

    bind.execute(text("UPDATE pupils SET school_id = :demo_id WHERE is_demo = TRUE OR first_name = 'Demo'"), {'demo_id': demo_id})
    bind.execute(text("UPDATE pupils SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})

    result_tables = (
        'subject_results',
        'writing_results',
        'gap_scores',
        'interventions',
        'reception_tracker_entries',
        'phonics_scores',
        'times_table_scores',
        'foundation_results',
        'sats_column_results',
        'sats_results',
        'sats_writing_results',
    )
    for table_name in result_tables:
        if not (_has_table(bind, table_name) and _has_column(bind, table_name, 'school_id') and _has_column(bind, table_name, 'pupil_id')):
            continue
        bind.execute(text(
            f"UPDATE {table_name} SET school_id = (SELECT pupils.school_id FROM pupils WHERE pupils.id = {table_name}.pupil_id) "
            f"WHERE pupil_id IS NOT NULL"
        ))
        bind.execute(text(f"UPDATE {table_name} SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})

    if _has_table(bind, 'assessment_settings') and _has_column(bind, 'assessment_settings', 'school_id'):
        bind.execute(text("UPDATE assessment_settings SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})

    if _has_table(bind, 'tracker_mode_settings') and _has_column(bind, 'tracker_mode_settings', 'school_id'):
        bind.execute(text("UPDATE tracker_mode_settings SET school_id = :barrow_id WHERE school_id IS NULL"), {'barrow_id': barrow_id})


def _enforce_is_admin_defaults(bind) -> None:
    if not (_has_table(bind, 'users') and _has_column(bind, 'users', 'is_admin')):
        return

    bind.execute(text("""
        UPDATE users
        SET is_admin = CASE
            WHEN role IN ('school_admin', 'admin', 'executive_admin') THEN TRUE
            ELSE FALSE
        END
        WHERE is_admin IS NULL
    """))

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('is_admin', existing_type=sa.Boolean(), nullable=False, server_default=sa.false())


def upgrade():
    bind = op.get_bind()

    _ensure_school_ids_on_settings(bind)

    barrow_id = bind.execute(text("SELECT id FROM schools WHERE slug='barrow-school' LIMIT 1")).scalar()
    if not barrow_id:
        bind.execute(text("INSERT INTO schools (name, slug, is_active, is_demo) VALUES ('Barrow School', 'barrow-school', TRUE, FALSE)"))
        barrow_id = bind.execute(text("SELECT id FROM schools WHERE slug='barrow-school' LIMIT 1")).scalar()

    demo_id = bind.execute(text("SELECT id FROM schools WHERE slug='demo-school' LIMIT 1")).scalar()
    if not demo_id:
        bind.execute(text("INSERT INTO schools (name, slug, is_active, is_demo) VALUES ('Demo School', 'demo-school', TRUE, TRUE)"))
        demo_id = bind.execute(text("SELECT id FROM schools WHERE slug='demo-school' LIMIT 1")).scalar()

    _force_school_backfill(bind, demo_id, barrow_id)
    _enforce_is_admin_defaults(bind)


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, 'users') and _has_column(bind, 'users', 'is_admin'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.alter_column('is_admin', existing_type=sa.Boolean(), nullable=True, server_default=None)
