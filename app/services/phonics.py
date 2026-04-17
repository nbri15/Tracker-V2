"""Service helpers for KS1 phonics tracker."""

from __future__ import annotations

from app.extensions import db
from app.models import PhonicsScore, PhonicsTestColumn, Pupil

KS1_YEAR_GROUPS = {1, 2}
DEFAULT_PHONICS_COLUMNS = ('Test 1', 'Test 2', 'Test 3', 'Test 4')


class PhonicsValidationError(ValueError):
    """Raised when phonics tracker input is invalid."""


def is_ks1_year_group(year_group: int | None) -> bool:
    return year_group in KS1_YEAR_GROUPS


def ensure_phonics_columns(year_group: int) -> list[PhonicsTestColumn]:
    columns = (
        PhonicsTestColumn.query
        .filter_by(year_group=year_group)
        .order_by(PhonicsTestColumn.display_order, PhonicsTestColumn.id)
        .all()
    )
    if columns:
        return columns

    for display_order, name in enumerate(DEFAULT_PHONICS_COLUMNS, start=1):
        db.session.add(
            PhonicsTestColumn(
                year_group=year_group,
                name=name,
                display_order=display_order,
                is_active=True,
            )
        )
    db.session.flush()
    return (
        PhonicsTestColumn.query
        .filter_by(year_group=year_group)
        .order_by(PhonicsTestColumn.display_order, PhonicsTestColumn.id)
        .all()
    )


def _parse_score(raw_value: str, pupil: Pupil, column: PhonicsTestColumn) -> int | None:
    value = (raw_value or '').strip()
    if value == '':
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise PhonicsValidationError(f'{pupil.full_name} · {column.name}: score must be a whole number.') from exc
    if parsed < 0:
        raise PhonicsValidationError(f'{pupil.full_name} · {column.name}: score cannot be negative.')
    return parsed


def save_phonics_columns(year_group: int, form_data) -> list[PhonicsTestColumn]:
    columns = ensure_phonics_columns(year_group)
    for index, column in enumerate(columns, start=1):
        name = (form_data.get(f'column_name_{column.id}', '') or '').strip()
        column.name = name or f'Test {index}'
        display_raw = (form_data.get(f'display_order_{column.id}', '') or '').strip()
        try:
            column.display_order = int(display_raw or index)
        except ValueError as exc:
            raise PhonicsValidationError(f'{column.name}: display order must be a whole number.') from exc
        column.is_active = form_data.get(f'is_active_{column.id}') == 'on'
        db.session.add(column)

    ids = {column.id for column in columns}
    if len(ids) != len(columns):
        raise PhonicsValidationError('Duplicate phonics columns detected.')

    return sorted(columns, key=lambda item: (item.display_order, item.id))


def add_phonics_column(year_group: int, form_data) -> PhonicsTestColumn:
    columns = ensure_phonics_columns(year_group)
    name = (form_data.get('new_column_name', '') or '').strip() or f'Test {len(columns) + 1}'
    display_raw = (form_data.get('new_column_order', '') or '').strip()
    try:
        display_order = int(display_raw or (len(columns) + 1))
    except ValueError as exc:
        raise PhonicsValidationError('New column order must be a whole number.') from exc

    column = PhonicsTestColumn(
        year_group=year_group,
        name=name,
        display_order=display_order,
        is_active=True,
    )
    db.session.add(column)
    db.session.flush()
    return column


def build_phonics_tracker_rows(pupils: list[Pupil], columns: list[PhonicsTestColumn], academic_year: str) -> list[dict]:
    column_ids = [column.id for column in columns]
    score_rows = (
        PhonicsScore.query
        .filter(
            PhonicsScore.academic_year == academic_year,
            PhonicsScore.pupil_id.in_([pupil.id for pupil in pupils]) if pupils else False,
            PhonicsScore.phonics_test_column_id.in_(column_ids) if column_ids else False,
        )
        .all()
    ) if pupils and columns else []
    score_lookup = {(row.pupil_id, row.phonics_test_column_id): row for row in score_rows}

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


def save_phonics_scores(pupils: list[Pupil], columns: list[PhonicsTestColumn], academic_year: str, form_data) -> None:
    pupil_ids = [pupil.id for pupil in pupils]
    column_ids = [column.id for column in columns]
    existing_rows = (
        PhonicsScore.query
        .filter(
            PhonicsScore.academic_year == academic_year,
            PhonicsScore.pupil_id.in_(pupil_ids) if pupil_ids else False,
            PhonicsScore.phonics_test_column_id.in_(column_ids) if column_ids else False,
        )
        .all()
    ) if pupils and columns else []
    existing_lookup = {(row.pupil_id, row.phonics_test_column_id): row for row in existing_rows}

    for pupil in pupils:
        for column in columns:
            score = _parse_score(form_data.get(f'score_{pupil.id}_{column.id}', ''), pupil, column)
            existing = existing_lookup.get((pupil.id, column.id))
            if score is None:
                if existing:
                    db.session.delete(existing)
                continue
            record = existing or PhonicsScore(
                pupil_id=pupil.id,
                academic_year=academic_year,
                phonics_test_column_id=column.id,
            )
            record.score = score
            db.session.add(record)
