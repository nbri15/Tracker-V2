"""Flexible SATs tracker services."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models import Pupil, SatsColumnResult, SatsColumnSetting, SchoolClass, TrackerModeSetting

SATS_TRACKER_MODES = {
    'normal': 'Usual tracker',
    'sats': 'SATs tracker',
}
SATS_COLUMN_SUBJECTS = [
    ('reading', 'Reading'),
    ('spag', 'SPaG'),
    ('arithmetic', 'Arithmetic'),
    ('maths', 'Maths'),
]
DEFAULT_YEAR6_SATS_COLUMNS = [
    {'name': 'Autumn Reading 1', 'subject': 'reading', 'max_marks': 50, 'pass_percentage': 60.0, 'display_order': 1, 'is_active': True},
    {'name': 'Autumn SPaG 1', 'subject': 'spag', 'max_marks': 50, 'pass_percentage': 60.0, 'display_order': 2, 'is_active': True},
    {'name': 'Autumn Arithmetic 1', 'subject': 'arithmetic', 'max_marks': 40, 'pass_percentage': 60.0, 'display_order': 3, 'is_active': True},
    {'name': 'Spring Mock Reading', 'subject': 'reading', 'max_marks': 50, 'pass_percentage': 60.0, 'display_order': 4, 'is_active': True},
    {'name': 'Spring Mock SPaG', 'subject': 'spag', 'max_marks': 50, 'pass_percentage': 60.0, 'display_order': 5, 'is_active': True},
    {'name': 'Pre-SATs Arithmetic', 'subject': 'arithmetic', 'max_marks': 40, 'pass_percentage': 60.0, 'display_order': 6, 'is_active': True},
]


class SatsColumnValidationError(ValueError):
    """Raised when a SATs column payload is invalid."""


def quantize_percent(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def get_tracker_mode(year_group: int) -> str:
    if year_group != 6:
        return 'normal'
    setting = TrackerModeSetting.query.filter_by(year_group=year_group).first()
    if setting:
        return setting.tracker_mode
    setting = TrackerModeSetting(year_group=year_group, tracker_mode='sats')
    db.session.add(setting)
    db.session.flush()
    return setting.tracker_mode


def set_tracker_mode(year_group: int, tracker_mode: str) -> TrackerModeSetting:
    if tracker_mode not in SATS_TRACKER_MODES:
        raise SatsColumnValidationError('Choose a valid Year 6 tracker mode.')
    setting = TrackerModeSetting.query.filter_by(year_group=year_group).first()
    if not setting:
        setting = TrackerModeSetting(year_group=year_group)
    setting.tracker_mode = tracker_mode
    db.session.add(setting)
    db.session.flush()
    return setting


def get_tracker_mode_label(year_group: int) -> str:
    return SATS_TRACKER_MODES[get_tracker_mode(year_group)]


def ensure_default_sats_columns(year_group: int = 6) -> list[SatsColumnSetting]:
    existing = SatsColumnSetting.query.filter_by(year_group=year_group).order_by(SatsColumnSetting.display_order, SatsColumnSetting.id).all()
    if existing:
        return existing
    for row in DEFAULT_YEAR6_SATS_COLUMNS:
        db.session.add(SatsColumnSetting(year_group=year_group, **row))
    db.session.flush()
    return SatsColumnSetting.query.filter_by(year_group=year_group).order_by(SatsColumnSetting.display_order, SatsColumnSetting.id).all()


def get_sats_columns(year_group: int = 6, *, active_only: bool = False) -> list[SatsColumnSetting]:
    query = SatsColumnSetting.query.filter_by(year_group=year_group)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(SatsColumnSetting.display_order, SatsColumnSetting.id).all()


def _coerce_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value == '':
        return None
    return int(value)


def validate_sats_column_payload(payload: dict) -> dict:
    cleaned = payload.copy()
    cleaned['name'] = cleaned.get('name', '').strip()
    cleaned['subject'] = cleaned.get('subject', '').strip().lower()
    cleaned['max_marks'] = int(cleaned.get('max_marks', 0))
    cleaned['pass_percentage'] = float(cleaned.get('pass_percentage', 0))
    cleaned['display_order'] = int(cleaned.get('display_order', 0))
    cleaned['is_active'] = bool(cleaned.get('is_active', True))

    if not cleaned['name']:
        raise SatsColumnValidationError('SATs column name is required.')
    if cleaned['subject'] not in {value for value, _ in SATS_COLUMN_SUBJECTS}:
        raise SatsColumnValidationError('Choose a valid SATs subject.')
    if cleaned['max_marks'] <= 0:
        raise SatsColumnValidationError('Max marks must be greater than 0.')
    if not 0 <= cleaned['pass_percentage'] <= 100:
        raise SatsColumnValidationError('Pass percentage must be between 0 and 100.')
    if cleaned['display_order'] <= 0:
        raise SatsColumnValidationError('Display order must be 1 or higher.')
    return cleaned


def save_sats_column(year_group: int, payload: dict, column_id: int | None = None) -> SatsColumnSetting:
    cleaned = validate_sats_column_payload(payload)
    column = SatsColumnSetting.query.get(column_id) if column_id else None
    if column_id and not column:
        raise SatsColumnValidationError('SATs column not found.')
    if not column:
        column = SatsColumnSetting(year_group=year_group)
    column.year_group = year_group
    for field, value in cleaned.items():
        setattr(column, field, value)
    db.session.add(column)
    db.session.flush()
    return column


def toggle_sats_column(column_id: int) -> SatsColumnSetting:
    column = SatsColumnSetting.query.get_or_404(column_id)
    column.is_active = not column.is_active
    db.session.add(column)
    db.session.flush()
    return column


def _result_lookup(rows: list[SatsColumnResult]) -> dict[tuple[int, int], SatsColumnResult]:
    return {(row.pupil_id, row.column_id): row for row in rows}


def build_sats_subject_summaries(columns: list[SatsColumnSetting], results: list[SatsColumnResult]) -> dict[str, dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {'total_raw': 0, 'total_max': 0, 'percent': None, 'pass_count': 0, 'column_count': 0, 'latest_score': None, 'latest_column_name': None})
    result_by_column = {result.column_id: result for result in results}
    for column in columns:
        subject = grouped[column.subject]
        subject['total_max'] += column.max_marks
        subject['column_count'] += 1
        result = result_by_column.get(column.id)
        if result and result.raw_score is not None:
            subject['total_raw'] += result.raw_score
            pass_mark = column.max_marks * (column.pass_percentage / 100)
            if result.raw_score >= pass_mark:
                subject['pass_count'] += 1
            subject['latest_score'] = result.raw_score
            subject['latest_column_name'] = column.name
    for summary in grouped.values():
        if summary['total_max']:
            summary['percent'] = quantize_percent((summary['total_raw'] / summary['total_max']) * 100)
    return grouped


def build_sats_tracker_rows(pupils: list[Pupil], academic_year: str, year_group: int = 6, *, active_only: bool = True) -> tuple[list[SatsColumnSetting], list[dict], dict]:
    columns = get_sats_columns(year_group, active_only=active_only)
    pupil_ids = [pupil.id for pupil in pupils]
    results = (
        SatsColumnResult.query.filter(
            SatsColumnResult.academic_year == academic_year,
            SatsColumnResult.pupil_id.in_(pupil_ids or [0]),
            SatsColumnResult.column_id.in_([column.id for column in columns] or [0]),
        )
        .all()
        if pupils and columns
        else []
    )
    lookup = _result_lookup(results)
    rows = []
    overview_totals: dict[str, dict] = defaultdict(lambda: {'total_raw': 0, 'total_max': 0, 'pupil_count': 0, 'pass_count': 0, 'column_count': 0})
    for pupil in pupils:
        pupil_results = [row for row in results if row.pupil_id == pupil.id]
        subject_summaries = build_sats_subject_summaries(columns, pupil_results)
        rows.append({
            'pupil': pupil,
            'results': {column.id: lookup.get((pupil.id, column.id)) for column in columns},
            'subject_summaries': subject_summaries,
        })
        for subject, summary in subject_summaries.items():
            overview = overview_totals[subject]
            overview['total_raw'] += summary['total_raw']
            overview['total_max'] += summary['total_max']
            overview['pass_count'] += summary['pass_count']
            overview['column_count'] = max(overview['column_count'], summary['column_count'])
            overview['pupil_count'] += 1
    for summary in overview_totals.values():
        summary['average_percent'] = quantize_percent((summary['total_raw'] / summary['total_max']) * 100) if summary['total_max'] else None
    return columns, rows, dict(overview_totals)


def save_sats_tracker_results(pupils: list[Pupil], academic_year: str, columns: list[SatsColumnSetting], form_data) -> None:
    for pupil in pupils:
        for column in columns:
            raw_score = _coerce_int(form_data.get(f'column_{column.id}_{pupil.id}', ''))
            existing = SatsColumnResult.query.filter_by(pupil_id=pupil.id, column_id=column.id, academic_year=academic_year).first()
            if raw_score is None:
                if existing:
                    db.session.delete(existing)
                continue
            if raw_score < 0 or raw_score > column.max_marks:
                raise SatsColumnValidationError(f'{pupil.full_name}: {column.name} must be between 0 and {column.max_marks}.')
            result = existing or SatsColumnResult(pupil_id=pupil.id, column_id=column.id, academic_year=academic_year)
            result.raw_score = raw_score
            db.session.add(result)


def build_year6_sats_overview(academic_year: str, class_id: int | None = None) -> dict:
    query = SchoolClass.query.filter_by(year_group=6, is_active=True)
    if class_id:
        query = query.filter(SchoolClass.id == class_id)
    classes = query.order_by(SchoolClass.name).all()
    class_summaries = []
    all_rows = []
    columns = get_sats_columns(6, active_only=True)
    for school_class in classes:
        pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
        _, rows, subject_totals = build_sats_tracker_rows(pupils, academic_year, 6, active_only=True)
        all_rows.extend(rows)
        class_summaries.append({'class': school_class, 'rows': rows, 'subject_totals': subject_totals})
    return {'columns': columns, 'rows': all_rows, 'class_summaries': class_summaries}
