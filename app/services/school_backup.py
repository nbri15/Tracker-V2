"""One-click full backup of a single school's data as a ZIP of CSV files.

Safety rules:
* Every exported table is restricted to the given school. A table with no way of
  being tied to a school is never exported; it is listed as "not included".
* Password hashes are never written to the backup.
* Text cells that a spreadsheet could treat as a formula get a leading apostrophe.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.extensions import db

# Columns that must never appear in a backup file.
EXCLUDED_COLUMNS: dict[str, set[str]] = {'users': {'password_hash'}}

# Tables with no school link that are small shared reference data and safe to include whole.
SHARED_REFERENCE_TABLES = {'academic_years'}

# Shared content or bookkeeping tables that are not school data (question banks, migration marker).
NOT_SCHOOL_DATA = {'alembic_version', 'fundamental_strands', 'fundamental_levels', 'fundamental_questions'}

_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='replace')
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def scoped_select(table, school_id: int):
    """Return a SELECT limited to the school's rows, or None if the table can't be scoped."""
    name, cols = table.name, table.c
    if name in NOT_SCHOOL_DATA:
        return None
    selected = [c for c in cols if c.name not in EXCLUDED_COLUMNS.get(name, set())]
    base = select(*selected)
    if name == 'schools':
        return base.where(cols.id == school_id)
    if name in SHARED_REFERENCE_TABLES:
        return base
    if 'school_id' in cols:
        return base.where(cols.school_id == school_id)
    # Maths Fundamentals tables have no school column; reach the school through the class.
    if name == 'fundamental_sessions':
        classes = db.metadata.tables['school_classes']
        return base.where(cols.class_id.in_(select(classes.c.id).where(classes.c.school_id == school_id)))
    if name == 'fundamental_pupil_attempts':
        sessions = db.metadata.tables['fundamental_sessions']
        classes = db.metadata.tables['school_classes']
        session_ids = select(sessions.c.id).where(
            sessions.c.class_id.in_(select(classes.c.id).where(classes.c.school_id == school_id))
        )
        return base.where(cols.session_id.in_(session_ids))
    if name == 'fundamental_responses':
        attempts = db.metadata.tables['fundamental_pupil_attempts']
        sessions = db.metadata.tables['fundamental_sessions']
        classes = db.metadata.tables['school_classes']
        session_ids = select(sessions.c.id).where(
            sessions.c.class_id.in_(select(classes.c.id).where(classes.c.school_id == school_id))
        )
        attempt_ids = select(attempts.c.id).where(attempts.c.session_id.in_(session_ids))
        return base.where(cols.attempt_id.in_(attempt_ids))
    return None


def unscoped_tables() -> list[str]:
    """Names of tables the backup cannot tie to a school (and so does not export)."""
    return sorted(
        table.name for table in db.metadata.sorted_tables
        if table.name not in NOT_SCHOOL_DATA and scoped_select(table, 0) is None
    )


def build_school_backup(school_id: int, school_name: str, extra_files: dict[str, bytes] | None = None):
    """Return ``(zip_bytes, row_counts)`` for one school."""

    counts: dict[str, int] = {}
    buffer = io.BytesIO()
    generated = datetime.now(timezone.utc)
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for table in db.metadata.sorted_tables:
            statement = scoped_select(table, school_id)
            if statement is None:
                continue
            out = io.StringIO(newline='')
            writer = csv.writer(out)
            writer.writerow([column.name for column in statement.selected_columns])
            rows = 0
            for row in db.session.execute(statement):
                writer.writerow([_cell(value) for value in row])
                rows += 1
            counts[table.name] = rows
            archive.writestr(f'data/{table.name}.csv', out.getvalue())
        for filename, content in (extra_files or {}).items():
            archive.writestr(filename, content)
        archive.writestr('README.txt', _readme(school_name, generated, counts, sorted(extra_files or {})))
    return buffer.getvalue(), counts


def _readme(school_name: str, generated: datetime, counts: dict[str, int], extra_names: list[str]) -> str:
    lines = [
        'CLASS COMPASS - FULL SCHOOL BACKUP',
        f'School: {school_name}',
        f'Created (UTC): {generated.strftime("%Y-%m-%d %H:%M")}',
        '',
        'THIS FILE CONTAINS REAL PUPIL DATA. Keep it only on school-approved storage.',
        'Do not email it, put it on a personal device, or upload it to GitHub.',
        'Delete old copies you no longer need.',
        '',
        'What is inside',
        '- data/*.csv: one file per table, limited to this school.',
    ]
    if 'school_workbook.xlsx' in extra_names:
        lines.append('- school_workbook.xlsx: the school workbook in the same format used for imports.')
    lines += [
        '',
        'Not included',
        '- Password hashes. Users must be given new passwords if the data is ever restored.',
        '- Shared content such as the Maths Fundamentals question bank.',
        "- Text starting with = + - or @ has an apostrophe added at the start so spreadsheets do not treat it as a formula.",
        '',
        'Row counts',
    ]
    lines += [f'- {name}: {count}' for name, count in sorted(counts.items())]
    skipped = unscoped_tables()
    if skipped:
        lines += ['', 'Tables that could not be tied to a school and were skipped'] + [f'- {name}' for name in skipped]
    return '\n'.join(lines) + '\n'
