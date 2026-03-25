"""Flexible SATs tracker services."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models import Pupil, SatsColumnResult, SatsColumnSetting, SatsExamTab, SchoolClass, TrackerModeSetting

SATS_TRACKER_MODES = {
    'normal': 'Usual tracker',
    'sats': 'SATs tracker',
}
SATS_COLUMN_SUBJECTS = [
    ('maths', 'Maths'),
    ('reading', 'Reading'),
    ('spag', 'SPaG'),
]
SATS_SCORE_TYPES = {
    'paper': 'Paper score',
    'raw': 'Raw score (auto)',
    'scaled': 'Scaled score',
}
DEFAULT_YEAR6_TAB_NAMES = ['Autumn 1', 'Autumn 2', 'Spring 1', 'Spring 2', 'Spring Mock', 'Pre-SATs', 'Summer']
DEFAULT_EXAM_TAB_COLUMNS = [
    {'name': 'Arithmetic', 'subject': 'maths', 'score_type': 'paper', 'column_key': 'maths_arithmetic', 'max_marks': 40},
    {'name': 'Reasoning 1', 'subject': 'maths', 'score_type': 'paper', 'column_key': 'maths_reasoning_1', 'max_marks': 35},
    {'name': 'Reasoning 2', 'subject': 'maths', 'score_type': 'paper', 'column_key': 'maths_reasoning_2', 'max_marks': 35},
    {'name': 'Maths Raw Score', 'subject': 'maths', 'score_type': 'raw', 'column_key': 'maths_raw_total', 'max_marks': 110},
    {'name': 'Maths Scaled Score', 'subject': 'maths', 'score_type': 'scaled', 'column_key': 'maths_scaled', 'max_marks': 120},
    {'name': 'Reading Paper', 'subject': 'reading', 'score_type': 'paper', 'column_key': 'reading_paper', 'max_marks': 50},
    {'name': 'Reading Raw Score', 'subject': 'reading', 'score_type': 'raw', 'column_key': 'reading_raw_total', 'max_marks': 50},
    {'name': 'Reading Scaled Score', 'subject': 'reading', 'score_type': 'scaled', 'column_key': 'reading_scaled', 'max_marks': 120},
    {'name': 'SPaG Paper 1', 'subject': 'spag', 'score_type': 'paper', 'column_key': 'spag_paper_1', 'max_marks': 35},
    {'name': 'SPaG Paper 2', 'subject': 'spag', 'score_type': 'paper', 'column_key': 'spag_paper_2', 'max_marks': 35},
    {'name': 'SPaG Raw Score', 'subject': 'spag', 'score_type': 'raw', 'column_key': 'spag_raw_total', 'max_marks': 70},
    {'name': 'SPaG Scaled Score', 'subject': 'spag', 'score_type': 'scaled', 'column_key': 'spag_scaled', 'max_marks': 120},
]
CALCULATION_KEY_MAP = {
    'maths_raw_total': ['maths_arithmetic', 'maths_reasoning_1', 'maths_reasoning_2'],
    'reading_raw_total': ['reading_paper'],
    'spag_raw_total': ['spag_paper_1', 'spag_paper_2'],
}


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


def _next_tab_order(year_group: int) -> int:
    highest = db.session.query(db.func.max(SatsExamTab.display_order)).filter(SatsExamTab.year_group == year_group).scalar()
    return (highest or 0) + 1


def _next_column_order(tab_id: int) -> int:
    highest = db.session.query(db.func.max(SatsColumnSetting.display_order)).filter(SatsColumnSetting.exam_tab_id == tab_id).scalar()
    return (highest or 0) + 1


def create_exam_tab_with_defaults(year_group: int, name: str, *, display_order: int | None = None, is_active: bool = True) -> SatsExamTab:
    exam_tab = SatsExamTab(
        year_group=year_group,
        name=name.strip(),
        display_order=display_order or _next_tab_order(year_group),
        is_active=is_active,
    )
    db.session.add(exam_tab)
    db.session.flush()
    for order, row in enumerate(DEFAULT_EXAM_TAB_COLUMNS, start=1):
        db.session.add(
            SatsColumnSetting(
                year_group=year_group,
                exam_tab_id=exam_tab.id,
                name=row['name'],
                subject=row['subject'],
                score_type=row['score_type'],
                column_key=row['column_key'],
                max_marks=row['max_marks'],
                pass_percentage=60.0,
                display_order=order,
                is_active=True,
            )
        )
    db.session.flush()
    return exam_tab


def ensure_default_sats_columns(year_group: int = 6) -> list[SatsColumnSetting]:
    tabs = get_sats_exam_tabs(year_group, include_inactive=True)
    if not tabs:
        for order, name in enumerate(DEFAULT_YEAR6_TAB_NAMES, start=1):
            create_exam_tab_with_defaults(year_group, name, display_order=order)
    return get_sats_columns(year_group, active_only=False)


def get_sats_exam_tabs(year_group: int = 6, *, include_inactive: bool = False) -> list[SatsExamTab]:
    query = SatsExamTab.query.filter_by(year_group=year_group)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query.order_by(SatsExamTab.display_order, SatsExamTab.id).all()


def get_sats_columns(year_group: int = 6, *, exam_tab_id: int | None = None, active_only: bool = False) -> list[SatsColumnSetting]:
    query = SatsColumnSetting.query.filter_by(year_group=year_group)
    if exam_tab_id:
        query = query.filter_by(exam_tab_id=exam_tab_id)
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
    cleaned['score_type'] = cleaned.get('score_type', 'paper').strip().lower()
    cleaned['max_marks'] = int(cleaned.get('max_marks', 0))
    cleaned['pass_percentage'] = float(cleaned.get('pass_percentage', 0))
    cleaned['display_order'] = int(cleaned.get('display_order', 0))
    cleaned['is_active'] = bool(cleaned.get('is_active', True))

    if not cleaned['name']:
        raise SatsColumnValidationError('SATs column name is required.')
    if cleaned['subject'] not in {value for value, _ in SATS_COLUMN_SUBJECTS}:
        raise SatsColumnValidationError('Choose a valid SATs subject.')
    if cleaned['score_type'] not in SATS_SCORE_TYPES:
        raise SatsColumnValidationError('Choose a valid SATs score type.')
    if cleaned['max_marks'] <= 0:
        raise SatsColumnValidationError('Max marks must be greater than 0.')
    if not 0 <= cleaned['pass_percentage'] <= 100:
        raise SatsColumnValidationError('Pass percentage must be between 0 and 100.')
    if cleaned['display_order'] <= 0:
        raise SatsColumnValidationError('Display order must be 1 or higher.')
    return cleaned


def save_sats_column(year_group: int, exam_tab_id: int, payload: dict, column_id: int | None = None) -> SatsColumnSetting:
    cleaned = validate_sats_column_payload(payload)
    column = SatsColumnSetting.query.get(column_id) if column_id else None
    if column_id and not column:
        raise SatsColumnValidationError('SATs column not found.')
    if not column:
        column = SatsColumnSetting(year_group=year_group, exam_tab_id=exam_tab_id)
    column.year_group = year_group
    column.exam_tab_id = exam_tab_id
    for field, value in cleaned.items():
        setattr(column, field, value)
    # User-created columns should not claim default calculation keys.
    if not column_id:
        column.column_key = None
    db.session.add(column)
    db.session.flush()
    return column


def save_sats_tab(payload: dict, tab_id: int | None = None) -> SatsExamTab:
    tab = SatsExamTab.query.get(tab_id) if tab_id else None
    if tab_id and not tab:
        raise SatsColumnValidationError('SATs exam tab not found.')
    name = payload.get('name', '').strip()
    if not name:
        raise SatsColumnValidationError('Exam tab name is required.')
    display_order = int(payload.get('display_order', 0) or 0)
    if display_order <= 0:
        raise SatsColumnValidationError('Exam tab order must be 1 or higher.')
    is_active = bool(payload.get('is_active', True))
    if not tab:
        tab = create_exam_tab_with_defaults(int(payload.get('year_group', 6)), name, display_order=display_order, is_active=is_active)
    else:
        tab.name = name
        tab.display_order = display_order
        tab.is_active = is_active
        db.session.add(tab)
        db.session.flush()
    return tab


def toggle_sats_column(column_id: int) -> SatsColumnSetting:
    column = SatsColumnSetting.query.get_or_404(column_id)
    column.is_active = not column.is_active
    db.session.add(column)
    db.session.flush()
    return column


def toggle_sats_tab(tab_id: int) -> SatsExamTab:
    tab = SatsExamTab.query.get_or_404(tab_id)
    tab.is_active = not tab.is_active
    db.session.add(tab)
    db.session.flush()
    return tab


def _result_lookup(rows: list[SatsColumnResult]) -> dict[tuple[int, int], SatsColumnResult]:
    return {(row.pupil_id, row.column_id): row for row in rows}


def _calc_column_value(column_map: dict[str, SatsColumnSetting], row_lookup: dict[tuple[int, int], SatsColumnResult], pupil_id: int, key: str) -> int | None:
    target = column_map.get(key)
    if not target:
        return None
    source_keys = CALCULATION_KEY_MAP.get(key, [])
    values: list[int] = []
    for source_key in source_keys:
        source_col = column_map.get(source_key)
        if not source_col:
            continue
        source_result = row_lookup.get((pupil_id, source_col.id))
        if source_result and source_result.raw_score is not None:
            values.append(source_result.raw_score)
    if not values:
        return None
    return sum(values)


def build_sats_tracker_rows(
    pupils: list[Pupil],
    academic_year: str,
    year_group: int = 6,
    *,
    exam_tab_id: int | None = None,
    active_only: bool = True,
) -> tuple[list[SatsColumnSetting], list[dict], dict]:
    tabs = get_sats_exam_tabs(year_group, include_inactive=True)
    if not tabs:
        ensure_default_sats_columns(year_group)
        tabs = get_sats_exam_tabs(year_group, include_inactive=True)
    selected_tab = next((tab for tab in tabs if tab.id == exam_tab_id), None)
    if not selected_tab:
        selected_tab = next((tab for tab in tabs if tab.is_active), tabs[0] if tabs else None)
    columns = get_sats_columns(year_group, exam_tab_id=selected_tab.id if selected_tab else None, active_only=active_only)

    pupil_ids = [pupil.id for pupil in pupils]
    results = (
        SatsColumnResult.query.filter(
            SatsColumnResult.academic_year == academic_year,
            SatsColumnResult.pupil_id.in_(pupil_ids or [0]),
            SatsColumnResult.column_id.in_([column.id for column in columns] or [0]),
        ).all()
        if pupils and columns
        else []
    )
    lookup = _result_lookup(results)
    rows = []
    overview_totals: dict[str, dict] = defaultdict(lambda: {'total_raw': 0, 'total_max': 0, 'pupil_count': 0, 'pass_count': 0, 'column_count': 0})
    key_map = {column.column_key: column for column in columns if column.column_key}

    for pupil in pupils:
        calculated_values = {
            key: _calc_column_value(key_map, lookup, pupil.id, key)
            for key in CALCULATION_KEY_MAP
        }
        rows.append({
            'pupil': pupil,
            'results': {column.id: lookup.get((pupil.id, column.id)) for column in columns},
            'calculated_values': calculated_values,
        })

        for column in columns:
            if column.score_type != 'raw':
                continue
            value = calculated_values.get(column.column_key)
            if value is None:
                continue
            overview = overview_totals[column.subject]
            overview['total_raw'] += value
            overview['total_max'] += column.max_marks
            overview['column_count'] += 1
            overview['pupil_count'] += 1
            pass_mark = column.max_marks * (column.pass_percentage / 100)
            if value >= pass_mark:
                overview['pass_count'] += 1

    for summary in overview_totals.values():
        summary['average_percent'] = quantize_percent((summary['total_raw'] / summary['total_max']) * 100) if summary['total_max'] else None

    return columns, rows, dict(overview_totals | {'_selected_tab': selected_tab, '_tabs': tabs})


def save_sats_tracker_results(pupils: list[Pupil], academic_year: str, columns: list[SatsColumnSetting], form_data) -> None:
    column_by_key = {column.column_key: column for column in columns if column.column_key}

    for pupil in pupils:
        manual_values: dict[int, int | None] = {}
        for column in columns:
            existing = SatsColumnResult.query.filter_by(pupil_id=pupil.id, column_id=column.id, academic_year=academic_year).first()

            if column.score_type == 'raw':
                # Auto-calculated fields are persisted after manual entries are parsed.
                continue

            raw_score = _coerce_int(form_data.get(f'column_{column.id}_{pupil.id}', ''))
            if raw_score is None:
                if existing:
                    db.session.delete(existing)
                manual_values[column.id] = None
                continue
            if raw_score < 0 or raw_score > column.max_marks:
                raise SatsColumnValidationError(f'{pupil.full_name}: {column.name} must be between 0 and {column.max_marks}.')
            result = existing or SatsColumnResult(pupil_id=pupil.id, column_id=column.id, academic_year=academic_year)
            result.raw_score = raw_score
            db.session.add(result)
            manual_values[column.id] = raw_score

        # Persist computed raw totals per tab.
        for raw_key, source_keys in CALCULATION_KEY_MAP.items():
            raw_column = column_by_key.get(raw_key)
            if not raw_column:
                continue
            source_values = []
            for source_key in source_keys:
                source_column = column_by_key.get(source_key)
                if not source_column:
                    continue
                source_value = manual_values.get(source_column.id)
                if source_value is not None:
                    source_values.append(source_value)
            existing_raw = SatsColumnResult.query.filter_by(pupil_id=pupil.id, column_id=raw_column.id, academic_year=academic_year).first()
            if not source_values:
                if existing_raw:
                    db.session.delete(existing_raw)
                continue
            raw_total = sum(source_values)
            if raw_total > raw_column.max_marks:
                raise SatsColumnValidationError(f'{pupil.full_name}: {raw_column.name} total exceeds max mark {raw_column.max_marks}.')
            row = existing_raw or SatsColumnResult(pupil_id=pupil.id, column_id=raw_column.id, academic_year=academic_year)
            row.raw_score = raw_total
            db.session.add(row)


def build_year6_sats_overview(academic_year: str, class_id: int | None = None, exam_tab_id: int | None = None) -> dict:
    query = SchoolClass.query.filter_by(year_group=6, is_active=True)
    if class_id:
        query = query.filter(SchoolClass.id == class_id)
    classes = query.order_by(SchoolClass.name).all()
    class_summaries = []
    all_rows = []

    tabs = get_sats_exam_tabs(6, include_inactive=True)
    selected_tab = next((tab for tab in tabs if tab.id == exam_tab_id), None)
    if not selected_tab:
        selected_tab = next((tab for tab in tabs if tab.is_active), tabs[0] if tabs else None)
    columns = get_sats_columns(6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=True)

    for school_class in classes:
        pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
        _, rows, subject_totals = build_sats_tracker_rows(pupils, academic_year, 6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=True)
        all_rows.extend(rows)
        class_summaries.append({'class': school_class, 'rows': rows, 'subject_totals': subject_totals})
    return {'columns': columns, 'rows': all_rows, 'class_summaries': class_summaries, 'tabs': tabs, 'selected_tab': selected_tab}
