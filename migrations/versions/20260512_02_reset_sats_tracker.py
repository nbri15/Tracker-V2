"""Backup and reset SATs tracker to fixed Exam 1-4 structure."""
from alembic import op
import sqlalchemy as sa

revision = '20260512_02_reset_sats_tracker'
down_revision = '20260512_01'
branch_labels = None
depends_on = None

FIXED_COLUMNS = [
    ('Arithmetic', 'maths', 'paper', 'maths_arithmetic', 40, 1),
    ('Reasoning 1', 'maths', 'paper', 'maths_reasoning_1', 35, 2),
    ('Reasoning 2', 'maths', 'paper', 'maths_reasoning_2', 35, 3),
    ('Maths Combined Score', 'maths', 'raw', 'maths_raw_total', 110, 4),
    ('Maths Scaled Score', 'maths', 'scaled', 'maths_scaled', 120, 5),
    ('Reading Paper', 'reading', 'paper', 'reading_paper', 50, 6),
    ('Reading Scaled Score', 'reading', 'scaled', 'reading_scaled', 120, 7),
    ('Spelling Paper', 'spag', 'paper', 'spag_spelling', 20, 8),
    ('Grammar Paper', 'spag', 'paper', 'spag_grammar', 50, 9),
    ('SPaG Combined Score', 'spag', 'raw', 'spag_raw_total', 70, 10),
    ('SPaG Scaled Score', 'spag', 'scaled', 'spag_scaled', 120, 11),
]

def _backup_table(conn, table_name):
    conn.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {table_name}_backup_20260512 AS TABLE {table_name}"))

def upgrade():
    conn = op.get_bind()
    for t in ['sats_results', 'sats_column_results', 'sats_column_settings', 'sats_exam_tabs', 'sats_writing_results']:
        _backup_table(conn, t)

    conn.execute(sa.text('DELETE FROM sats_column_results'))
    conn.execute(sa.text('DELETE FROM sats_column_settings'))
    conn.execute(sa.text('DELETE FROM sats_exam_tabs'))
    conn.execute(sa.text('DELETE FROM sats_writing_results'))
    conn.execute(sa.text('DELETE FROM sats_results'))

    schools = [row[0] for row in conn.execute(sa.text('SELECT id FROM schools')).fetchall()]
    for school_id in schools:
        for exam_number in range(1, 5):
            tab_res = conn.execute(sa.text(
                "INSERT INTO sats_exam_tabs (school_id, year_group, name, display_order, is_active, created_at, updated_at) "
                "VALUES (:school_id, 6, :name, :order_no, true, NOW(), NOW()) RETURNING id"
            ), {'school_id': school_id, 'name': f'Exam {exam_number}', 'order_no': exam_number})
            tab_id = tab_res.scalar()
            for name, subject, score_type, column_key, max_marks, display_order in FIXED_COLUMNS:
                conn.execute(sa.text(
                    "INSERT INTO sats_column_settings (school_id, year_group, exam_tab_id, name, subject, score_type, column_key, max_marks, pass_percentage, display_order, is_active, created_at, updated_at) "
                    "VALUES (:school_id, 6, :tab_id, :name, :subject, :score_type, :column_key, :max_marks, 60.0, :display_order, true, NOW(), NOW())"
                ), dict(school_id=school_id, tab_id=tab_id, name=name, subject=subject, score_type=score_type, column_key=column_key, max_marks=max_marks, display_order=display_order))


def downgrade():
    pass
