"""Service helpers for Year 4 times tables tracker."""

from __future__ import annotations

from app.extensions import db
from app.models import Pupil, TimesTableScore, TimesTableTestColumn

TIMES_TABLES_YEAR_GROUP = 4
DEFAULT_TIMES_TABLE_COLUMNS = ('Test 1', 'Test 2', 'Test 3', 'Test 4')


class TimesTablesValidationError(ValueError):
    """Raised when times tables tracker input is invalid."""


def is_times_tables_year_group(year_group: int | None) -> bool:
    return year_group == TIMES_TABLES_YEAR_GROUP


def ensure_times_tables_columns(year_group: int) -> list[TimesTableTestColumn]:
    columns = (
        TimesTableTestColumn.query
        .filter_by(year_group=year_group)
        .order_by(TimesTableTestColumn.display_order, TimesTableTestColumn.id)
        .all()
    )
    if columns:
        return columns

    for display_order, name in enumerate(DEFAULT_TIMES_TABLE_COLUMNS, start=1):
        db.session.add(
            TimesTableTestColumn(
                year_group=year_group,
                name=name,
                display_order=display_order,
                is_active=True,
            )
        )
    db.session.flush()
    return (
        TimesTableTestColumn.query
        .filter_by(year_group=year_group)
        .order_by(TimesTableTestColumn.display_order, TimesTableTestColumn.id)
        .all()
    )


def _parse_score(raw_value: str, pupil: Pupil, column: TimesTableTestColumn) -> int | None:
    value = (raw_value or '').strip()
    if value == '':
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise TimesTablesValidationError(f'{pupil.full_name} · {column.name}: score must be a whole number.') from exc
    if parsed < 0:
        raise TimesTablesValidationError(f'{pupil.full_name} · {column.name}: score cannot be negative.')
    return parsed


def save_times_tables_columns(year_group: int, form_data) -> list[TimesTableTestColumn]:
    columns = ensure_times_tables_columns(year_group)
    for index, column in enumerate(columns, start=1):
        name = (form_data.get(f'column_name_{column.id}', '') or '').strip()
        column.name = name or f'Test {index}'
        display_raw = (form_data.get(f'display_order_{column.id}', '') or '').strip()
        try:
            column.display_order = int(display_raw or index)
        except ValueError as exc:
            raise TimesTablesValidationError(f'{column.name}: display order must be a whole number.') from exc
        column.is_active = form_data.get(f'is_active_{column.id}') == 'on'
        db.session.add(column)

    ids = {column.id for column in columns}
    if len(ids) != len(columns):
        raise TimesTablesValidationError('Duplicate times tables columns detected.')

    return sorted(columns, key=lambda item: (item.display_order, item.id))


def add_times_tables_column(year_group: int, form_data) -> TimesTableTestColumn:
    columns = ensure_times_tables_columns(year_group)
    name = (form_data.get('new_column_name', '') or '').strip() or f'Test {len(columns) + 1}'
    display_raw = (form_data.get('new_column_order', '') or '').strip()
    try:
        display_order = int(display_raw or (len(columns) + 1))
    except ValueError as exc:
        raise TimesTablesValidationError('New column order must be a whole number.') from exc

    column = TimesTableTestColumn(
        year_group=year_group,
        name=name,
        display_order=display_order,
        is_active=True,
    )
    db.session.add(column)
    db.session.flush()
    return column


def build_times_tables_tracker_rows(pupils: list[Pupil], columns: list[TimesTableTestColumn], academic_year: str) -> list[dict]:
    column_ids = [column.id for column in columns]
    score_rows = (
        TimesTableScore.query
        .filter(
            TimesTableScore.academic_year == academic_year,
            TimesTableScore.pupil_id.in_([pupil.id for pupil in pupils]) if pupils else False,
            TimesTableScore.times_table_test_column_id.in_(column_ids) if column_ids else False,
        )
        .all()
    ) if pupils and columns else []
    score_lookup = {(row.pupil_id, row.times_table_test_column_id): row for row in score_rows}

    rows: list[dict] = []
    for pupil in pupils:
        values: dict[int, int | None] = {}
        latest_score = None
        for column in columns:
            record = score_lookup.get((pupil.id, column.id))
            value = record.score if record else None
            values[column.id] = value
            if column.is_active and value is not None:
                latest_score = value

        flags = []
        if pupil.pupil_premium:
            flags.append('PP')
        if pupil.laps:
            flags.append('LAPS')
        if pupil.service_child:
            flags.append('Service')
        rows.append({'pupil': pupil, 'scores': values, 'latest_score': latest_score, 'flags': ' · '.join(flags) if flags else '—'})
    return rows


def save_times_tables_scores(pupils: list[Pupil], columns: list[TimesTableTestColumn], academic_year: str, form_data) -> None:
    pupil_ids = [pupil.id for pupil in pupils]
    column_ids = [column.id for column in columns]
    existing_rows = (
        TimesTableScore.query
        .filter(
            TimesTableScore.academic_year == academic_year,
            TimesTableScore.pupil_id.in_(pupil_ids) if pupil_ids else False,
            TimesTableScore.times_table_test_column_id.in_(column_ids) if column_ids else False,
        )
        .all()
    ) if pupils and columns else []
    existing_lookup = {(row.pupil_id, row.times_table_test_column_id): row for row in existing_rows}

    for pupil in pupils:
        for column in columns:
            score = _parse_score(form_data.get(f'score_{pupil.id}_{column.id}', ''), pupil, column)
            existing = existing_lookup.get((pupil.id, column.id))
            if score is None:
                if existing:
                    db.session.delete(existing)
                continue
            record = existing or TimesTableScore(
                pupil_id=pupil.id,
                academic_year=academic_year,
                times_table_test_column_id=column.id,
            )
            record.score = score
            db.session.add(record)


def sort_times_tables_tracker_rows(rows: list[dict], sort_column: str, sort_direction: str) -> list[dict]:
    reverse = sort_direction == 'desc'
    if sort_column == 'name':
        return sorted(
            rows,
            key=lambda row: (
                row['pupil'].last_name.lower(),
                row['pupil'].first_name.lower(),
                row['pupil'].id,
            ),
            reverse=reverse,
        )
    if sort_column.startswith('column_'):
        try:
            column_id = int(sort_column.split('_', 1)[1])
        except (TypeError, ValueError):
            return sorted(
                rows,
                key=lambda row: (
                    row['pupil'].last_name.lower(),
                    row['pupil'].first_name.lower(),
                    row['pupil'].id,
                ),
            )
        populated = [row for row in rows if row['scores'].get(column_id) is not None]
        empty = sorted(
            [row for row in rows if row['scores'].get(column_id) is None],
            key=lambda row: (
                row['pupil'].last_name.lower(),
                row['pupil'].first_name.lower(),
                row['pupil'].id,
            ),
        )
        populated = sorted(
            populated,
            key=lambda row: (
                row['scores'].get(column_id),
                row['pupil'].last_name.lower(),
                row['pupil'].first_name.lower(),
                row['pupil'].id,
            ),
            reverse=reverse,
        )
        return (populated + empty) if reverse else (empty + populated)
    return sorted(
        rows,
        key=lambda row: (
            row['pupil'].last_name.lower(),
            row['pupil'].first_name.lower(),
            row['pupil'].id,
        ),
    )
