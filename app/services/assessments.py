"""Assessment and dashboard service helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    AssessmentSetting,
    Intervention,
    PhonicsScore,
    PhonicsTestColumn,
    Pupil,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SatsColumnSetting,
    SatsExamTab,
    SatsResult,
    SatsWritingResult,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    TimesTableTestColumn,
    WritingResult,
)

TERMS = [
    ('autumn', 'Autumn'),
    ('spring', 'Spring'),
    ('summer', 'Summer'),
]
TERM_SEQUENCE = {term: index for index, (term, _) in enumerate(TERMS, start=1)}
CORE_SUBJECTS = ('maths', 'reading', 'spag')
ALL_SUBJECTS = (*CORE_SUBJECTS, 'writing')
SUBJECT_DISPLAY_NAMES = {
    'maths': 'Maths',
    'reading': 'Reading',
    'spag': 'SPaG',
    'writing': 'Writing',
}
WRITING_BAND_CHOICES = [
    ('working_towards', 'Working Towards'),
    ('expected', 'Expected'),
    ('greater_depth', 'Greater Depth'),
]
WRITING_BAND_LABELS = dict(WRITING_BAND_CHOICES)
SORT_OPTIONS = {
    'name_asc': 'Pupil name A–Z',
    'name_desc': 'Pupil name Z–A',
    'percent_desc': 'Highest combined percent',
    'percent_asc': 'Lowest combined percent',
    'band_asc': 'Band A–Z',
}
RESULT_OUTCOME_THEMES = {
    'Working Towards': 'wt',
    'On Track': 'ot',
    'Working At': 'ot',
    'Expected': 'ot',
    'Exceeding': 'ex',
    'Greater Depth': 'ex',
}
RESULT_THEME_ORDER = {'wt': 0, 'ot': 1, 'ex': 2}
CLASS_SORT_OPTIONS = {
    'year_group': 'Year group',
    'class_name': 'Class name',
    'teacher_name': 'Teacher',
    'pupil_count_desc': 'Pupil count (high to low)',
    'pupil_count_asc': 'Pupil count (low to high)',
    'maths_ot_plus_desc': 'Maths OT+ (high to low)',
    'reading_ot_plus_desc': 'Reading OT+ (high to low)',
    'spag_ot_plus_desc': 'SPaG OT+ (high to low)',
    'writing_ot_plus_desc': 'Writing OT+ (high to low)',
}
SUBGROUP_FILTERS = {
    'all': 'All pupils',
    'pp': 'Pupil Premium',
    'laps': 'LAPS',
    'service_child': 'Service child',
}
BOOLEAN_FILTER_CHOICES = {
    'all': 'All',
    'yes': 'Yes',
    'no': 'No',
}
SATS_SUBJECTS = ('reading', 'maths', 'spag')
SATS_ASSESSMENT_POINTS = (1, 2, 3, 4)

SUBJECT_DEFAULTS = {
    'maths': {
        'paper_1_name': 'Arithmetic',
        'paper_1_max': 40,
        'paper_2_name': 'Reasoning',
        'paper_2_max': 35,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 45.0,
        'exceeding_threshold_percent': 80.0,
    },
    'reading': {
        'paper_1_name': 'Paper 1',
        'paper_1_max': 30,
        'paper_2_name': 'Paper 2',
        'paper_2_max': 20,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 45.0,
        'exceeding_threshold_percent': 80.0,
    },
    'spag': {
        'paper_1_name': 'Spelling',
        'paper_1_max': 20,
        'paper_2_name': 'Grammar',
        'paper_2_max': 30,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 45.0,
        'exceeding_threshold_percent': 80.0,
    },
}


class AssessmentValidationError(ValueError):
    """Raised when assessment inputs are invalid."""


class CsvImportError(ValueError):
    """Raised when CSV input is invalid."""


def format_subject_name(subject: str) -> str:
    return SUBJECT_DISPLAY_NAMES.get(subject, subject.replace('_', ' ').title())


def get_term_label(term: str) -> str:
    return dict(TERMS).get(term, term.title())


def get_writing_band_label(band: str | None) -> str:
    if not band:
        return '—'
    return WRITING_BAND_LABELS.get(band, band.replace('_', ' ').title())


def get_result_outcome_theme(band_label: str | None) -> str | None:
    if not band_label:
        return None
    return RESULT_OUTCOME_THEMES.get(band_label)


def get_writing_outcome_theme(band: str | None) -> str | None:
    return get_result_outcome_theme(get_writing_band_label(band))


def get_current_academic_year(today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    year = today.year
    start_year = year if today.month >= 9 else year - 1
    return f'{start_year}/{str(start_year + 1)[-2:]}'


def get_current_term(today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    if today.month >= 9:
        return 'autumn'
    if 1 <= today.month < 4:
        return 'spring'
    return 'summer'


def build_academic_year_options(current_year: str, total_years: int = 4) -> list[str]:
    start_year = int(current_year.split('/')[0])
    years = [f'{year}/{str(year + 1)[-2:]}' for year in range(start_year - 1, start_year - 1 + total_years)]
    if current_year not in years:
        years.append(current_year)
    return sorted(set(years), reverse=True)


def get_setting_defaults(subject: str) -> dict:
    defaults = SUBJECT_DEFAULTS[subject].copy()
    defaults['combined_max'] = defaults['paper_1_max'] + defaults['paper_2_max']
    return defaults


def validate_setting_payload(data: dict) -> dict:
    cleaned = data.copy()
    cleaned['paper_1_name'] = cleaned['paper_1_name'].strip() or 'Paper 1'
    cleaned['paper_2_name'] = cleaned['paper_2_name'].strip() or 'Paper 2'

    calculated_combined = cleaned['paper_1_max'] + cleaned['paper_2_max']
    combined_max = cleaned.get('combined_max')
    cleaned['combined_max'] = combined_max or calculated_combined

    if cleaned['paper_1_max'] < 0 or cleaned['paper_2_max'] < 0 or cleaned['combined_max'] <= 0:
        raise AssessmentValidationError('Max scores must be zero or above, and combined max must be greater than 0.')

    below = float(cleaned['below_are_threshold_percent'])
    exceeding = float(cleaned['exceeding_threshold_percent'])
    on_track = float(cleaned.get('on_track_threshold_percent', below))
    if not 0 <= below <= 100 or not 0 <= exceeding <= 100 or not 0 <= on_track <= 100:
        raise AssessmentValidationError('Threshold percentages must be between 0 and 100.')
    if below > exceeding:
        raise AssessmentValidationError('Working Towards threshold must be less than or equal to the Exceeding threshold.')

    cleaned['below_are_threshold_percent'] = below
    cleaned['on_track_threshold_percent'] = on_track
    cleaned['exceeding_threshold_percent'] = exceeding
    return cleaned


def get_or_create_assessment_setting(year_group: int, subject: str, term: str) -> AssessmentSetting:
    setting = AssessmentSetting.query.filter_by(year_group=year_group, subject=subject, term=term).first()
    if setting:
        return setting

    defaults = get_setting_defaults(subject)
    setting = AssessmentSetting(year_group=year_group, subject=subject, term=term, **defaults)
    db.session.add(setting)
    db.session.flush()
    return setting


def get_subject_setting(year_group: int, subject: str, term: str) -> AssessmentSetting:
    return get_or_create_assessment_setting(year_group, subject, term)


def update_assessment_setting(setting: AssessmentSetting, payload: dict) -> AssessmentSetting:
    for field, value in payload.items():
        setattr(setting, field, value)
    db.session.add(setting)
    return setting


def compute_subject_result_values(
    setting: AssessmentSetting,
    paper_1_score: int | None,
    paper_2_score: int | None,
    *,
    validate_scores: bool = True,
) -> dict:
    for label, score, max_score in (
        (setting.paper_1_name, paper_1_score, setting.paper_1_max),
        (setting.paper_2_name, paper_2_score, setting.paper_2_max),
    ):
        if score is None or not validate_scores:
            continue
        if score < 0:
            raise AssessmentValidationError(f'{label} score cannot be below 0.')
        if score > max_score:
            raise AssessmentValidationError(f'{label} score cannot exceed {max_score}.')

    combined_score = SubjectResult.calculate_combined_score(paper_1_score, paper_2_score)
    combined_percent = SubjectResult.calculate_percent(combined_score, setting.combined_max)
    band_label = SubjectResult.calculate_band_label(combined_percent, setting.below_are_threshold_percent, setting.exceeding_threshold_percent)
    return {
        'combined_score': combined_score,
        'combined_percent': combined_percent,
        'band_label': band_label,
    }


def resolve_effective_assessment_year_group(result_year_group: int | None, pupil_year_group: int | None) -> int | None:
    if result_year_group is not None:
        return result_year_group
    return pupil_year_group


def resolve_subject_band_label(
    *,
    percent: float | None,
    setting: AssessmentSetting | None,
    pupil_year_group: int | None,
    assessment_year_group: int | None,
) -> str | None:
    if percent is None or setting is None:
        return None
    effective_test_year = resolve_effective_assessment_year_group(assessment_year_group, pupil_year_group)
    if pupil_year_group is not None and effective_test_year is not None and effective_test_year < pupil_year_group:
        return 'Working Towards'
    return SubjectResult.calculate_band_label(
        percent,
        setting.below_are_threshold_percent,
        setting.exceeding_threshold_percent,
    )


def format_progress_delta(delta: float | None) -> str:
    if delta is None:
        return '—'
    rounded = int(round(delta))
    if rounded > 0:
        return f'↑ +{rounded}'
    if rounded < 0:
        return f'↓ {rounded}'
    return '→ 0'


def progress_theme(delta: float | None) -> str | None:
    if delta is None:
        return None
    if delta > 0:
        return 'up'
    if delta < 0:
        return 'down'
    return 'flat'


def previous_term(term: str) -> str | None:
    order = [key for key, _ in TERMS]
    if term not in order:
        return None
    idx = order.index(term)
    if idx <= 0:
        return None
    return order[idx - 1]


def recalculate_subject_results_for_scope(year_group: int, subject: str, term: str, *, academic_year: str | None = None, class_id: int | None = None) -> int:
    setting = get_subject_setting(year_group, subject, term)
    query = (
        SubjectResult.query.join(SubjectResult.pupil).join(Pupil.school_class)
        .options(joinedload(SubjectResult.pupil).joinedload(Pupil.school_class))
        .filter(SubjectResult.subject == subject, SubjectResult.term == term, SchoolClass.year_group == year_group)
    )
    if academic_year:
        query = query.filter(SubjectResult.academic_year == academic_year)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)

    results = query.all()
    for result in results:
        if result.paper_1_score is None or result.paper_2_score is None:
            continue
        computed = compute_subject_result_values(setting, result.paper_1_score, result.paper_2_score, validate_scores=False)
        result.combined_score = computed['combined_score']
        result.combined_percent = computed['combined_percent']
        result.band_label = computed['band_label']
        db.session.add(result)
    return len(results)


def apply_pupil_subgroup(query, subgroup: str):
    if subgroup == 'pp':
        return query.filter(Pupil.pupil_premium.is_(True))
    if subgroup == 'laps':
        return query.filter(Pupil.laps.is_(True))
    if subgroup == 'service_child':
        return query.filter(Pupil.service_child.is_(True))
    return query


def apply_admin_pupil_filters(query, filters: dict | None = None):
    filters = filters or {}

    pupil_status = (filters.get('pupil_status') or 'active').strip().lower()
    if pupil_status == 'active':
        query = query.filter(Pupil.is_active.is_(True))
    elif pupil_status == 'archived':
        query = query.filter(Pupil.is_active.is_(False))

    gender = (filters.get('gender') or '').strip()
    if gender and gender != 'all':
        query = query.filter(Pupil.gender == gender)

    for filter_name, field in (
        ('pupil_premium', Pupil.pupil_premium),
        ('laps', Pupil.laps),
        ('service_child', Pupil.service_child),
    ):
        value = (filters.get(filter_name) or '').strip()
        if value == 'yes':
            query = query.filter(field.is_(True))
        elif value == 'no':
            query = query.filter(field.is_(False))

    search = (filters.get('search') or '').strip()
    if search:
        search_term = f'%{search}%'
        query = query.filter(or_(Pupil.first_name.ilike(search_term), Pupil.last_name.ilike(search_term)))

    return query


def apply_pupil_filters(query, *, subgroup: str = 'all', filters: dict | None = None):
    query = apply_pupil_subgroup(query, subgroup)
    return apply_admin_pupil_filters(query, filters)


def build_admin_pupil_filter_state(args) -> dict:
    return {
        'pupil_status': (args.get('pupil_status', 'active') or 'active').strip() or 'active',
        'gender': (args.get('gender', 'all') or 'all').strip() or 'all',
        'pupil_premium': (args.get('pupil_premium', 'all') or 'all').strip() or 'all',
        'laps': (args.get('laps', 'all') or 'all').strip() or 'all',
        'service_child': (args.get('service_child', 'all') or 'all').strip() or 'all',
        'search': (args.get('search', '') or '').strip(),
    }


def build_table_sort_state(args, *, allowed_columns: set[str], default_column: str) -> dict:
    sort_column = (args.get('sort', default_column) or default_column).strip()
    if sort_column not in allowed_columns:
        sort_column = default_column
    sort_direction = (args.get('direction', 'asc') or 'asc').strip().lower()
    if sort_direction not in {'asc', 'desc'}:
        sort_direction = 'asc'
    return {'column': sort_column, 'direction': sort_direction}


def build_sort_indicator(column: str, sort_state: dict) -> str:
    if sort_state.get('column') != column:
        return ''
    return '↑' if sort_state.get('direction') == 'asc' else '↓'


def get_next_sort_direction(column: str, sort_state: dict) -> str:
    if sort_state.get('column') == column and sort_state.get('direction') == 'asc':
        return 'desc'
    return 'asc'


def _name_sort_key(row: dict) -> tuple:
    pupil = row.get('pupil')
    if pupil is not None:
        return (pupil.last_name.lower(), pupil.first_name.lower(), pupil.id)
    return ((row.get('name') or '').lower(),)


def _sort_rows(rows: list[dict], value_func, *, direction: str = 'asc') -> list[dict]:
    descending = direction == 'desc'
    populated = [row for row in rows if value_func(row) is not None]
    empty = sorted([row for row in rows if value_func(row) is None], key=_name_sort_key)
    populated = sorted(populated, key=lambda row: (value_func(row), _name_sort_key(row)), reverse=descending)
    return (populated + empty) if descending else (empty + populated)


def _coerce_numeric(value):
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace('%', '')
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalized_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def annotate_subject_result_rows(rows: list[dict]) -> list[dict]:
    annotated = []
    for row in rows:
        updated = row.copy()
        updated['outcome_theme'] = get_result_outcome_theme(updated.get('band_label'))
        annotated.append(updated)
    return annotated


def annotate_writing_result_rows(rows: list[dict]) -> list[dict]:
    annotated = []
    for row in rows:
        updated = row.copy()
        updated['band_label'] = updated.get('band_label') or get_writing_band_label(updated.get('band'))
        updated['outcome_theme'] = updated.get('outcome_theme') or get_result_outcome_theme(updated.get('band_label'))
        annotated.append(updated)
    return annotated


def sort_subject_result_rows(rows: list[dict], sort_column: str, sort_direction: str) -> list[dict]:
    reverse = sort_direction == 'desc'
    if sort_column == 'name':
        return sorted(rows, key=_name_sort_key, reverse=reverse)
    if sort_column == 'paper_1_score':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('paper_1_score')), direction=sort_direction)
    if sort_column == 'paper_2_score':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('paper_2_score')), direction=sort_direction)
    if sort_column == 'combined_score':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('combined_score')), direction=sort_direction)
    if sort_column == 'combined_percent':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('combined_percent')), direction=sort_direction)
    if sort_column == 'band_label':
        return _sort_rows(rows, lambda row: _normalized_text(row.get('band_label')), direction=sort_direction)
    if sort_column == 'assessment_year_group':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('assessment_year_group')), direction=sort_direction)
    if sort_column == 'progress_delta':
        return _sort_rows(rows, lambda row: _coerce_numeric(row.get('progress_delta')), direction=sort_direction)
    return sorted(rows, key=_name_sort_key)


def sort_writing_result_rows(rows: list[dict], sort_column: str, sort_direction: str) -> list[dict]:
    reverse = sort_direction == 'desc'
    if sort_column == 'name':
        return sorted(rows, key=_name_sort_key, reverse=reverse)
    if sort_column == 'band_label':
        return _sort_rows(rows, lambda row: _normalized_text(row.get('band_label')), direction=sort_direction)
    if sort_column == 'notes':
        return _sort_rows(rows, lambda row: _normalized_text(row.get('notes')), direction=sort_direction)
    return sorted(rows, key=_name_sort_key)


def get_gender_filter_options(*, class_id: int | None = None, include_inactive: bool = False) -> list[str]:
    query = db.session.query(Pupil.gender)
    if not include_inactive:
        query = query.filter(Pupil.is_active.is_(True))
    if class_id is not None:
        query = query.filter(Pupil.class_id == class_id)
    genders = [value for (value,) in query.distinct().order_by(Pupil.gender).all() if value]
    return genders


def _empty_subject_summary(subject: str) -> dict:
    return {
        'subject': subject,
        'subject_label': format_subject_name(subject),
        'term': None,
        'term_label': 'No data',
        'working_towards': 0,
        'on_track': 0,
        'exceeding': 0,
        'on_track_plus': 0,
        'pupil_count': 0,
        'filtered_pupil_count': 0,
        'average_percent': None,
        'working_towards_percent': 0.0,
        'on_track_percent': 0.0,
        'exceeding_percent': 0.0,
        'on_track_plus_percent': 0.0,
    }


def _build_summary_payload(
    subject: str,
    term: str | None,
    counts: dict[str, int],
    pupil_count: int,
    *,
    average_percent: float | None = None,
    filtered_pupil_count: int | None = None,
) -> dict:
    summary = _empty_subject_summary(subject)
    summary.update({
        'term': term,
        'term_label': get_term_label(term) if term else 'No data',
        'working_towards': counts['Working Towards'],
        'on_track': counts['On Track'],
        'exceeding': counts['Exceeding'],
        'on_track_plus': counts['On Track'] + counts['Exceeding'],
        'pupil_count': pupil_count,
        'filtered_pupil_count': filtered_pupil_count if filtered_pupil_count is not None else pupil_count,
        'average_percent': average_percent,
    })
    if pupil_count:
        summary['working_towards_percent'] = round((summary['working_towards'] / pupil_count) * 100, 1)
        summary['on_track_percent'] = round((summary['on_track'] / pupil_count) * 100, 1)
        summary['exceeding_percent'] = round((summary['exceeding'] / pupil_count) * 100, 1)
        summary['on_track_plus_percent'] = round((summary['on_track_plus'] / pupil_count) * 100, 1)
    return summary


def _counts_from_band_labels(rows: list[SubjectResult]) -> dict:
    counts = {'Working Towards': 0, 'On Track': 0, 'Exceeding': 0}
    setting_cache: dict[tuple[int, str, str], AssessmentSetting] = {}
    for row in rows:
        if row.combined_percent is None:
            continue
        year_group = row.pupil.school_class.year_group if row.pupil and row.pupil.school_class else None
        if year_group is None:
            band_label = row.band_label
        else:
            cache_key = (year_group, row.subject, row.term)
            setting = setting_cache.get(cache_key)
            if setting is None:
                setting = get_subject_setting(year_group, row.subject, row.term)
                setting_cache[cache_key] = setting
            band_label = resolve_subject_band_label(
                percent=row.combined_percent,
                setting=setting,
                pupil_year_group=year_group,
                assessment_year_group=row.assessment_year_group,
            )
        if band_label in counts:
            counts[band_label] += 1
    return counts


def _counts_from_writing_bands(rows: list[WritingResult]) -> dict:
    return {
        'Working Towards': sum(1 for row in rows if row.band == 'working_towards'),
        'On Track': sum(1 for row in rows if row.band == 'expected'),
        'Exceeding': sum(1 for row in rows if row.band == 'greater_depth'),
    }


def get_most_recent_term_with_data(
    class_id: int,
    subject: str,
    academic_year: str,
    subgroup: str = 'all',
    filters: dict | None = None,
) -> str | None:
    if subject in CORE_SUBJECTS:
        query = SubjectResult.query.join(SubjectResult.pupil).filter(
            SubjectResult.subject == subject,
            SubjectResult.academic_year == academic_year,
            SubjectResult.combined_percent.isnot(None),
            Pupil.class_id == class_id,
        )
    else:
        query = WritingResult.query.join(WritingResult.pupil).filter(
            WritingResult.academic_year == academic_year,
            WritingResult.band.isnot(None),
            Pupil.class_id == class_id,
        )
    rows = apply_pupil_filters(query, subgroup=subgroup, filters=filters).all()
    if not rows:
        return None
    return max(rows, key=lambda item: TERM_SEQUENCE.get(item.term, 0)).term


def compute_class_subject_summary(
    class_id: int,
    subject: str,
    academic_year: str,
    subgroup: str = 'all',
    *,
    filters: dict | None = None,
    term: str | None = None,
) -> dict:
    filtered_pupil_count = apply_admin_pupil_filters(
        Pupil.query.filter(Pupil.class_id == class_id, Pupil.is_active.is_(True)),
        filters,
    ).count()
    latest_term = term or get_most_recent_term_with_data(class_id, subject, academic_year, subgroup, filters)
    if not latest_term:
        summary = _empty_subject_summary(subject)
        summary['filtered_pupil_count'] = filtered_pupil_count
        return summary

    if subject in CORE_SUBJECTS:
        query = SubjectResult.query.join(SubjectResult.pupil).filter(
            SubjectResult.subject == subject,
            SubjectResult.academic_year == academic_year,
            SubjectResult.term == latest_term,
            Pupil.class_id == class_id,
        )
        latest_rows = apply_pupil_filters(query, subgroup=subgroup, filters=filters).all()
        counts = _counts_from_band_labels(latest_rows)
        percents = [row.combined_percent for row in latest_rows if row.combined_percent is not None]
    else:
        query = WritingResult.query.join(WritingResult.pupil).filter(
            WritingResult.academic_year == academic_year,
            WritingResult.term == latest_term,
            Pupil.class_id == class_id,
        )
        latest_rows = apply_pupil_filters(query, subgroup=subgroup, filters=filters).all()
        counts = _counts_from_writing_bands(latest_rows)
        percents = []

    return _build_summary_payload(
        subject,
        latest_term,
        counts,
        len(latest_rows),
        average_percent=round(sum(percents) / len(percents), 1) if percents else None,
        filtered_pupil_count=filtered_pupil_count,
    )


def build_dashboard_summary(class_id: int | None, academic_year: str, subgroup: str = 'all', filters: dict | None = None) -> list[dict]:
    if not class_id:
        return [_empty_subject_summary(subject) for subject in ALL_SUBJECTS]
    return [compute_class_subject_summary(class_id, subject, academic_year, subgroup, filters=filters) for subject in ALL_SUBJECTS]


def build_class_overview_row(school_class: SchoolClass, academic_year: str, subgroup: str = 'all', filters: dict | None = None) -> dict:
    pupil_query = school_class.pupils.filter_by(is_active=True)
    pupil_query = apply_pupil_filters(pupil_query, subgroup=subgroup, filters=filters)
    pupil_count = pupil_query.count()
    subject_summaries = {
        subject: compute_class_subject_summary(school_class.id, subject, academic_year, subgroup, filters=filters)
        for subject in ALL_SUBJECTS
    }
    active_interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(Intervention.is_active.is_(True), Intervention.academic_year == academic_year, Pupil.class_id == school_class.id)
        .filter(Pupil.is_active.is_(True))
    )
    active_interventions = apply_admin_pupil_filters(active_interventions, filters).count()
    return {
        'class': school_class,
        'class_id': school_class.id,
        'class_name': school_class.name,
        'year_group': school_class.year_group,
        'teacher_name': school_class.teacher.username if school_class.teacher else 'Unassigned',
        'pupil_count': pupil_count,
        'active_interventions': active_interventions,
        'subjects': subject_summaries,
    }


def sort_class_rows(class_rows: list[dict], sort: str) -> list[dict]:
    if sort == 'class_name':
        return sorted(class_rows, key=lambda row: (row['class_name'].lower(), row['year_group']))
    if sort == 'teacher_name':
        return sorted(class_rows, key=lambda row: (row['teacher_name'].lower(), row['class_name'].lower()))
    if sort == 'pupil_count_desc':
        return sorted(class_rows, key=lambda row: (-row['pupil_count'], row['class_name'].lower()))
    if sort == 'pupil_count_asc':
        return sorted(class_rows, key=lambda row: (row['pupil_count'], row['class_name'].lower()))
    if sort.endswith('_ot_plus_desc'):
        subject = sort.replace('_ot_plus_desc', '')
        return sorted(class_rows, key=lambda row: (-row['subjects'][subject]['on_track_plus'], row['class_name'].lower()))
    return sorted(class_rows, key=lambda row: (row['year_group'], row['class_name'].lower()))


def build_subject_overview_cards(class_rows: list[dict]) -> list[dict]:
    cards = []
    for subject in ALL_SUBJECTS:
        counts = {'Working Towards': 0, 'On Track': 0, 'Exceeding': 0}
        term_candidates = []
        filtered_pupil_total = 0
        for row in class_rows:
            summary = row['subjects'][subject]
            counts['Working Towards'] += summary['working_towards']
            counts['On Track'] += summary['on_track']
            counts['Exceeding'] += summary['exceeding']
            filtered_pupil_total += summary.get('filtered_pupil_count', row['pupil_count'])
            if summary['term']:
                term_candidates.append(summary['term'])
        latest_term = None
        if term_candidates:
            latest_term = max(term_candidates, key=lambda item: TERM_SEQUENCE.get(item, 0))
        card = _build_summary_payload(
            subject,
            latest_term,
            counts,
            sum(counts.values()),
            filtered_pupil_count=filtered_pupil_total,
        )
        cards.append(card)
    return cards


def _headline_empty_cell() -> dict:
    return {
        'count': 0,
        'total': 0,
        'percent': 0.0,
        'display': '—',
    }


def _headline_term_cell(*, count: int, total: int) -> dict:
    if total <= 0:
        return _headline_empty_cell()
    percent = round((count / total) * 100, 1)
    return {
        'count': count,
        'total': total,
        'percent': percent,
        'display': f'{percent:.1f}% ({count}/{total})',
    }


def _headline_measure_cell(*, count: int, total: int) -> dict:
    return _headline_term_cell(count=count, total=total)


def _finalize_headline_payload(
    *,
    subject: str,
    subject_label: str,
    academic_year: str,
    year_group: int | None,
    subgroup: str,
    bucket_keys: list[str],
    bucket_labels: dict[str, str],
    measure_labels: dict[str, str],
    row_header_label: str,
    rows: list[dict],
) -> dict:
    totals_by_bucket = {
        bucket: {'total': 0, **{measure: 0 for measure in measure_labels}}
        for bucket in bucket_keys
    }
    for row in rows:
        for bucket in bucket_keys:
            bucket_totals = row.get('bucket_totals', {}).get(bucket, {})
            totals_by_bucket[bucket]['total'] += bucket_totals.get('total', 0)
            for measure in measure_labels:
                totals_by_bucket[bucket][measure] += bucket_totals.get(measure, 0)

    return {
        'subject': subject,
        'subject_label': subject_label,
        'academic_year': academic_year,
        'year_group': year_group,
        'subgroup': subgroup,
        'row_header_label': row_header_label,
        'buckets': bucket_keys,
        'bucket_labels': bucket_labels,
        'measure_keys': tuple(measure_labels.keys()),
        'measure_labels': measure_labels,
        'rows': rows,
        'totals': {
            bucket: {
                measure: _headline_measure_cell(count=values[measure], total=values['total'])
                for measure in measure_labels
            }
            for bucket, values in totals_by_bucket.items()
        },
        # Backward-compatible aliases used by existing template/export logic.
        'terms': bucket_keys,
        'term_labels': bucket_labels,
    }


def build_headline_report(
    *,
    subject: str,
    academic_year: str,
    year_group: int | None = None,
    subgroup: str = 'all',
    filters: dict | None = None,
    tracker_key: str | None = None,
) -> dict:
    additional_subjects = {'eyfs', 'phonics', 'times_tables', 'sats'}
    if subject not in ALL_SUBJECTS and subject not in additional_subjects:
        subject = 'maths'
    filters = filters or {}
    measure_labels = {'working_towards': 'Working Towards', 'on_track_plus': 'On Track+', 'exceeding': 'Exceeding'}

    if subject in ALL_SUBJECTS:
        years = [year_group] if year_group in {1, 2, 3, 4, 5, 6} else [1, 2, 3, 4, 5, 6]
        terms = [term for term, _ in TERMS]
        query = (
            SubjectResult.query.join(SubjectResult.pupil).join(Pupil.school_class).filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SchoolClass.year_group.in_(years),
            )
        )
        if subject == 'writing':
            query = WritingResult.query.join(WritingResult.pupil).join(Pupil.school_class).filter(
                WritingResult.academic_year == academic_year,
                SchoolClass.year_group.in_(years),
            )
        query = apply_pupil_filters(query, subgroup=subgroup, filters=filters)
        score_rows = query.all()
        year_term_counts = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0}))
        for row in score_rows:
            if row.term not in terms:
                continue
            cell = year_term_counts[row.pupil.school_class.year_group][row.term]
            cell['total'] += 1
            if subject in CORE_SUBJECTS:
                setting = get_subject_setting(row.pupil.school_class.year_group, subject, row.term)
                band_label = SubjectResult.calculate_band_label(
                    row.combined_percent,
                    setting.below_are_threshold_percent,
                    setting.exceeding_threshold_percent,
                )
            else:
                band_label = None
            if subject in CORE_SUBJECTS and band_label == 'Exceeding':
                cell['exceeding'] += 1
                cell['on_track_plus'] += 1
            elif subject in CORE_SUBJECTS and band_label == 'On Track':
                cell['on_track_plus'] += 1
            elif subject == 'writing' and row.band == 'greater_depth':
                cell['exceeding'] += 1
                cell['on_track_plus'] += 1
            elif subject == 'writing' and row.band == 'expected':
                cell['on_track_plus'] += 1
            else:
                cell['working_towards'] += 1
        rows = []
        for year in years:
            bucket_totals = {term: year_term_counts[year][term] for term in terms}
            cells = {
                term: {measure: _headline_measure_cell(count=bucket_totals[term][measure], total=bucket_totals[term]['total']) for measure in measure_labels}
                for term in terms
            }
            rows.append({'label': f'Year {year}', 'year_group': year, 'cells': cells, 'bucket_totals': bucket_totals, 'terms': cells})
        return _finalize_headline_payload(
            subject=subject,
            subject_label=format_subject_name(subject),
            academic_year=academic_year,
            year_group=year_group,
            subgroup=subgroup,
            bucket_keys=terms,
            bucket_labels={value: label for value, label in TERMS},
            measure_labels=measure_labels,
            row_header_label='Year group',
            rows=rows,
        )

    if subject == 'eyfs':
        tracking_points = ['baseline', 'autumn_2', 'spring_1', 'spring_2', 'summer_1', 'elg']
        selected_point = tracker_key if tracker_key in tracking_points else None
        bucket_keys = [selected_point] if selected_point else tracking_points
        bucket_labels = {
            'baseline': 'Baseline',
            'autumn_2': 'Autumn 2',
            'spring_1': 'Spring 1',
            'spring_2': 'Spring 2',
            'summer_1': 'Summer 1',
            'elg': 'ELG',
        }
        eyfs_measures = {'not_on_track': 'Not on track', 'on_track': 'On Track'}
        query = (
            ReceptionTrackerEntry.query.join(ReceptionTrackerEntry.pupil).join(Pupil.school_class).filter(
                ReceptionTrackerEntry.academic_year == academic_year,
                SchoolClass.year_group == 0,
                ReceptionTrackerEntry.tracking_point.in_(bucket_keys),
            )
        )
        query = apply_pupil_filters(query, subgroup=subgroup, filters=filters)
        entries = query.all()
        bucket_totals = {point: {'total': 0, 'not_on_track': 0, 'on_track': 0} for point in bucket_keys}
        for entry in entries:
            totals = bucket_totals[entry.tracking_point]
            totals['total'] += 1
            if entry.status == 'on_track':
                totals['on_track'] += 1
            else:
                totals['not_on_track'] += 1
        cells = {
            point: {measure: _headline_measure_cell(count=bucket_totals[point][measure], total=bucket_totals[point]['total']) for measure in eyfs_measures}
            for point in bucket_keys
        }
        row = {'label': 'Reception', 'year_group': 0, 'cells': cells, 'bucket_totals': bucket_totals, 'terms': cells}
        return _finalize_headline_payload(
            subject=subject,
            subject_label='EYFS',
            academic_year=academic_year,
            year_group=0,
            subgroup=subgroup,
            bucket_keys=bucket_keys,
            bucket_labels=bucket_labels,
            measure_labels=eyfs_measures,
            row_header_label='Year group',
            rows=[row],
        ) | {'selected_tracker_key': selected_point}

    if subject == 'phonics':
        years = [year_group] if year_group in {1, 2} else [1, 2]
        columns = (
            PhonicsTestColumn.query.filter(PhonicsTestColumn.year_group.in_(years), PhonicsTestColumn.is_active.is_(True))
            .order_by(PhonicsTestColumn.year_group, PhonicsTestColumn.display_order, PhonicsTestColumn.id)
            .all()
        )
        selected_column = next((column for column in columns if str(column.id) == str(tracker_key)), None) if tracker_key else None
        bucket_key = str(selected_column.id) if selected_column else 'latest'
        bucket_labels = {bucket_key: selected_column.name if selected_column else 'Latest test'}
        band_labels = {'working_towards': 'Working Towards (<30)', 'on_track_plus': 'On Track+ (30-33)', 'exceeding': 'Exceeding (34+)'}
        rows = []
        for year in years:
            pupils_query = Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == year)
            pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
            pupils = pupils_query.all()
            pupil_ids = [pupil.id for pupil in pupils]
            year_columns = [column for column in columns if column.year_group == year]
            target_column = selected_column if selected_column and selected_column.year_group == year else (year_columns[-1] if year_columns else None)
            counts = {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0}
            if target_column and pupil_ids:
                scores = PhonicsScore.query.filter_by(academic_year=academic_year, phonics_test_column_id=target_column.id).filter(PhonicsScore.pupil_id.in_(pupil_ids)).all()
                for score in scores:
                    if score.score is None:
                        continue
                    counts['total'] += 1
                    if score.score >= 34:
                        counts['exceeding'] += 1
                    elif score.score >= 30:
                        counts['on_track_plus'] += 1
                    else:
                        counts['working_towards'] += 1
            cells = {bucket_key: {measure: _headline_measure_cell(count=counts[measure], total=counts['total']) for measure in band_labels}}
            rows.append({'label': f'Year {year}', 'year_group': year, 'cells': cells, 'bucket_totals': {bucket_key: counts}, 'terms': cells})
        return _finalize_headline_payload(
            subject=subject,
            subject_label='Phonics',
            academic_year=academic_year,
            year_group=year_group,
            subgroup=subgroup,
            bucket_keys=[bucket_key],
            bucket_labels=bucket_labels,
            measure_labels=band_labels,
            row_header_label='Year group',
            rows=rows,
        ) | {'selected_tracker_key': bucket_key}

    if subject == 'times_tables':
        years = [4]
        columns = (
            TimesTableTestColumn.query.filter_by(year_group=4, is_active=True)
            .order_by(TimesTableTestColumn.display_order, TimesTableTestColumn.id)
            .all()
        )
        selected_column = next((column for column in columns if str(column.id) == str(tracker_key)), None) if tracker_key else None
        target_column = selected_column or (columns[-1] if columns else None)
        bucket_key = str(target_column.id) if target_column else 'latest'
        bucket_labels = {bucket_key: target_column.name if target_column else 'Latest test'}
        band_labels = {'working_towards': 'Working Towards (<20)', 'on_track_plus': 'On Track+ (20-24)', 'exceeding': 'Exceeding (25)'}

        pupils_query = Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == 4)
        pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
        pupils = pupils_query.all()
        pupil_ids = [pupil.id for pupil in pupils]
        counts = {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0}
        if target_column and pupil_ids:
            scores = TimesTableScore.query.filter_by(academic_year=academic_year, times_table_test_column_id=target_column.id).filter(TimesTableScore.pupil_id.in_(pupil_ids)).all()
            for score in scores:
                if score.score is None:
                    continue
                counts['total'] += 1
                if score.score >= 25:
                    counts['exceeding'] += 1
                elif score.score >= 20:
                    counts['on_track_plus'] += 1
                else:
                    counts['working_towards'] += 1

        cells = {bucket_key: {measure: _headline_measure_cell(count=counts[measure], total=counts['total']) for measure in band_labels}}
        row = {'label': 'Year 4', 'year_group': 4, 'cells': cells, 'bucket_totals': {bucket_key: counts}, 'terms': cells}
        return _finalize_headline_payload(
            subject=subject,
            subject_label='Times Tables',
            academic_year=academic_year,
            year_group=4,
            subgroup=subgroup,
            bucket_keys=[bucket_key],
            bucket_labels=bucket_labels,
            measure_labels=band_labels,
            row_header_label='Year group',
            rows=[row],
        ) | {'selected_tracker_key': bucket_key}

    # SATs (Year 6 scaled score headlines).
    tabs = SatsExamTab.query.filter_by(year_group=6).order_by(SatsExamTab.display_order, SatsExamTab.id).all()
    selected_tab = next((tab for tab in tabs if str(tab.id) == str(tracker_key)), None) if tracker_key else None
    if not selected_tab:
        selected_tab = next((tab for tab in tabs if tab.is_active), tabs[-1] if tabs else None)
    scaled_columns = []
    if selected_tab:
        scaled_columns = (
            SatsColumnSetting.query.filter_by(year_group=6, exam_tab_id=selected_tab.id, score_type='scaled', is_active=True)
            .filter(SatsColumnSetting.column_key.in_(['maths_scaled', 'reading_scaled', 'spag_scaled']))
            .order_by(SatsColumnSetting.display_order, SatsColumnSetting.id)
            .all()
        )
    pupils_query = Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == 6)
    pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
    pupils = pupils_query.all()
    pupil_ids = [pupil.id for pupil in pupils]
    measure_labels = {'working_towards': 'Working Towards (<100)', 'on_track_plus': 'On Track+ (100-109)', 'exceeding': 'Exceeding (110+)'}
    bucket_keys = [column.column_key for column in scaled_columns] or ['maths_scaled', 'reading_scaled', 'spag_scaled']
    bucket_labels = {'maths_scaled': 'Maths scaled', 'reading_scaled': 'Reading scaled', 'spag_scaled': 'SPaG scaled'}
    bucket_totals = {bucket: {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0} for bucket in bucket_keys}
    if pupil_ids and scaled_columns:
        results = (
            SatsColumnResult.query.filter_by(academic_year=academic_year)
            .filter(SatsColumnResult.pupil_id.in_(pupil_ids), SatsColumnResult.column_id.in_([column.id for column in scaled_columns]))
            .all()
        )
        column_key_by_id = {column.id: column.column_key for column in scaled_columns}
        for result in results:
            score_value = result.raw_score
            if score_value is None:
                continue
            key = column_key_by_id.get(result.column_id)
            if key not in bucket_totals:
                continue
            bucket = bucket_totals[key]
            bucket['total'] += 1
            if score_value >= 110:
                bucket['exceeding'] += 1
            elif score_value >= 100:
                bucket['on_track_plus'] += 1
            else:
                bucket['working_towards'] += 1
    cells = {
        bucket: {
            measure: _headline_measure_cell(count=bucket_totals[bucket][measure], total=bucket_totals[bucket]['total'])
            for measure in measure_labels
        }
        for bucket in bucket_keys
    }
    row = {'label': 'Year 6', 'year_group': 6, 'cells': cells, 'bucket_totals': bucket_totals, 'terms': cells}
    return _finalize_headline_payload(
        subject='sats',
        subject_label='SATs',
        academic_year=academic_year,
        year_group=6,
        subgroup=subgroup,
        bucket_keys=bucket_keys,
        bucket_labels=bucket_labels,
        measure_labels=measure_labels,
        row_header_label='Year group',
        rows=[row],
    ) | {'selected_tracker_key': str(selected_tab.id) if selected_tab else ''}


def _build_recent_table_rows(school_class: SchoolClass, subject: str, academic_year: str) -> tuple[str, list[dict]]:
    latest_term = get_most_recent_term_with_data(school_class.id, subject, academic_year)
    if not latest_term:
        return 'No data', []

    if subject in CORE_SUBJECTS:
        setting = get_subject_setting(school_class.year_group, subject, latest_term)
        rows = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.term == latest_term,
                Pupil.class_id == school_class.id,
            )
            .order_by(Pupil.last_name, Pupil.first_name)
            .all()
        )
        formatted_rows = [
            {
                'pupil_name': row.pupil.full_name,
                'paper_1_score': row.paper_1_score,
                'paper_2_score': row.paper_2_score,
                'combined_score': row.combined_score,
                'combined_percent': row.combined_percent,
                'band_label': SubjectResult.calculate_band_label(
                    row.combined_percent,
                    setting.below_are_threshold_percent,
                    setting.exceeding_threshold_percent,
                ),
                'source': row.source,
            }
            for row in rows
        ]
    else:
        rows = (
            WritingResult.query.join(WritingResult.pupil)
            .filter(
                WritingResult.academic_year == academic_year,
                WritingResult.term == latest_term,
                Pupil.class_id == school_class.id,
            )
            .order_by(Pupil.last_name, Pupil.first_name)
            .all()
        )
        formatted_rows = [
            {
                'pupil_name': row.pupil.full_name,
                'band_label': get_writing_band_label(row.band),
                'notes': row.notes,
            }
            for row in rows
        ]
    return get_term_label(latest_term), formatted_rows


def _build_pupil_flag_summary(pupil: Pupil) -> str:
    flags = []
    if pupil.pupil_premium:
        flags.append('PP')
    if pupil.laps:
        flags.append('LAPS')
    if pupil.service_child:
        flags.append('Service')
    return ' · '.join(flags) if flags else '—'


def _build_class_detail_subject_rows(
    school_class: SchoolClass,
    subject: str,
    term: str,
    academic_year: str,
    filters: dict | None = None,
    *,
    sort_column: str = 'name',
    sort_direction: str = 'asc',
) -> tuple[list[Pupil], list[dict]]:
    pupils = apply_admin_pupil_filters(
        school_class.pupils,
        filters,
    ).order_by(Pupil.last_name, Pupil.first_name).all()

    if subject in CORE_SUBJECTS:
        setting = get_subject_setting(school_class.year_group, subject, term)
        prev_term = previous_term(term)
        result_rows = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.term == term,
                Pupil.class_id == school_class.id,
            )
        )
        result_rows = apply_admin_pupil_filters(result_rows, filters).all()
        result_lookup = {row.pupil_id: row for row in result_rows}
        previous_lookup: dict[int, SubjectResult] = {}
        if prev_term:
            previous_rows = (
                SubjectResult.query.join(SubjectResult.pupil)
                .filter(
                    SubjectResult.subject == subject,
                    SubjectResult.academic_year == academic_year,
                    SubjectResult.term == prev_term,
                    Pupil.class_id == school_class.id,
                )
            )
            previous_rows = apply_admin_pupil_filters(previous_rows, filters).all()
            previous_lookup = {row.pupil_id: row for row in previous_rows}
    else:
        result_rows = (
            WritingResult.query.join(WritingResult.pupil)
            .filter(
                WritingResult.academic_year == academic_year,
                WritingResult.term == term,
                Pupil.class_id == school_class.id,
            )
        )
        result_rows = apply_admin_pupil_filters(result_rows, filters).all()
        result_lookup = {row.pupil_id: row for row in result_rows}

    rows = []
    for pupil in pupils:
        result = result_lookup.get(pupil.id)
        base_row = {
            'pupil': pupil,
            'name': pupil.full_name,
            'gender': pupil.gender,
            'pupil_premium': pupil.pupil_premium,
            'laps': pupil.laps,
            'service_child': pupil.service_child,
            'flags': _build_pupil_flag_summary(pupil),
        }
        if subject in CORE_SUBJECTS:
            assessment_year_group = (
                result.assessment_year_group
                if result and result.assessment_year_group is not None
                else school_class.year_group
            )
            prev_percent = previous_lookup.get(pupil.id).combined_percent if previous_lookup.get(pupil.id) else None
            delta = (result.combined_percent - prev_percent) if (result and result.combined_percent is not None and prev_percent is not None) else None
            base_row.update({
                'paper_1_score': result.paper_1_score if result else None,
                'paper_2_score': result.paper_2_score if result else None,
                'combined_score': result.combined_score if result else None,
                'combined_percent': result.combined_percent if result else None,
                'band_label': resolve_subject_band_label(
                    percent=result.combined_percent if result else None,
                    setting=setting,
                    pupil_year_group=school_class.year_group,
                    assessment_year_group=assessment_year_group,
                ),
                'assessment_year_group': assessment_year_group,
                'below_expected_test': assessment_year_group < school_class.year_group if result else False,
                'progress_delta': delta,
                'progress_label': format_progress_delta(delta),
                'progress_theme': progress_theme(delta),
                'source': result.source if result else None,
            })
        else:
            base_row.update({
                'band_label': get_writing_band_label(result.band) if result else None,
                'notes': result.notes if result else None,
            })
        rows.append(base_row)
    if subject in CORE_SUBJECTS:
        rows = annotate_subject_result_rows(rows)
        rows = sort_subject_result_rows(rows, sort_column, sort_direction)
    else:
        rows = annotate_writing_result_rows(rows)
        rows = sort_writing_result_rows(rows, sort_column, sort_direction)
    return pupils, rows


def _build_class_detail_sats_rows(school_class: SchoolClass, academic_year: str, filters: dict | None = None) -> list[dict]:
    pupils = apply_admin_pupil_filters(
        school_class.pupils,
        filters,
    ).order_by(Pupil.last_name, Pupil.first_name).all()
    rows = []
    for pupil in pupils:
        row = {
            'pupil': pupil,
            'name': pupil.full_name,
            'gender': pupil.gender,
            'pupil_premium': pupil.pupil_premium,
            'laps': pupil.laps,
            'service_child': pupil.service_child,
            'flags': _build_pupil_flag_summary(pupil),
            'subjects': {},
        }
        for subject in SATS_SUBJECTS:
            subject_rows = SatsResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, subject=subject).all()
            row['subjects'][subject] = get_sats_subject_summary(subject_rows)
        writing_rows = SatsWritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year).all()
        row['writing'] = get_sats_writing_summary(writing_rows)
        rows.append(row)
    return rows


def build_year6_sats_summary(school_class: SchoolClass, academic_year: str) -> dict | None:
    if school_class.year_group != 6:
        return None

    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    rows = []
    for pupil in pupils:
        row = {'pupil': pupil, 'subjects': {}, 'writing': {}}
        for subject in SATS_SUBJECTS:
            subject_rows = SatsResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, subject=subject).all()
            row['subjects'][subject] = get_sats_subject_summary(subject_rows)
        writing_rows = SatsWritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year).all()
        row['writing'] = get_sats_writing_summary(writing_rows)
        rows.append(row)
    return {'rows': rows, 'academic_year': academic_year}


def get_class_detail_context(
    school_class: SchoolClass,
    academic_year: str,
    *,
    subject: str = 'maths',
    term: str | None = None,
    filters: dict | None = None,
    sort_column: str = 'name',
    sort_direction: str = 'asc',
) -> dict:
    filters = filters or {}
    available_subjects = list(ALL_SUBJECTS)
    if school_class.year_group == 6:
        available_subjects.append('sats')
    active_subject = subject if subject in available_subjects else 'maths'

    filtered_pupils = apply_admin_pupil_filters(
        school_class.pupils,
        filters,
    ).order_by(Pupil.last_name, Pupil.first_name).all()

    context = {
        'school_class': school_class,
        'available_subjects': available_subjects,
        'selected_subject': active_subject,
        'available_terms': TERMS,
        'selected_term': None,
        'filtered_pupil_count': len(filtered_pupils),
        'total_pupil_count': school_class.pupils.filter_by(is_active=True).count(),
        'filters': filters,
        'subject_summary': None,
        'pupil_rows': [],
        'sats_rows': [],
        'subject_label': format_subject_name(active_subject) if active_subject != 'sats' else 'SATs',
        'sats_summary': build_year6_sats_summary(school_class, academic_year) if school_class.year_group == 6 else None,
    }

    if active_subject == 'sats':
        context['sats_rows'] = _build_class_detail_sats_rows(school_class, academic_year, filters)
        return context

    active_term = term if term in TERM_SEQUENCE else get_most_recent_term_with_data(
        school_class.id,
        active_subject,
        academic_year,
        filters=filters,
    )
    if active_term is None:
        active_term = get_current_term()
    pupils, pupil_rows = _build_class_detail_subject_rows(
        school_class,
        active_subject,
        active_term,
        academic_year,
        filters,
        sort_column=sort_column,
        sort_direction=sort_direction,
    )
    context.update({
        'selected_term': active_term,
        'subject_summary': compute_class_subject_summary(
            school_class.id,
            active_subject,
            academic_year,
            filters=filters,
            term=active_term,
        ),
        'pupil_rows': pupil_rows,
        'filtered_pupil_count': len(pupils),
        'overview_cards': {
            'improved': [row for row in pupil_rows if row.get('progress_delta') is not None and row.get('progress_delta') > 0],
            'no_change': [row for row in pupil_rows if row.get('progress_delta') is not None and row.get('progress_delta') == 0],
            'dropped': [row for row in pupil_rows if row.get('progress_delta') is not None and row.get('progress_delta') < 0],
            'below_test': [row for row in pupil_rows if row.get('below_expected_test')],
        } if active_subject in CORE_SUBJECTS else None,
    })
    return context


def get_sats_subject_summary(rows: list[SatsResult]) -> dict:
    by_point = {row.assessment_point: row for row in rows}
    latest_scaled = get_latest_scaled_score(rows)
    return {
        'points': {
            point: {'raw_score': by_point.get(point).raw_score if by_point.get(point) else None, 'scaled_score': by_point.get(point).scaled_score if by_point.get(point) else None}
            for point in SATS_ASSESSMENT_POINTS
        },
        'latest_scaled': latest_scaled,
    }


def get_sats_writing_summary(rows: list[SatsWritingResult]) -> dict:
    by_point = {row.assessment_point: row for row in rows}
    latest_row = max((row for row in rows if row.band), key=lambda row: row.assessment_point, default=None)
    return {
        'points': {
            point: {'band': by_point.get(point).band if by_point.get(point) else None, 'notes': by_point.get(point).notes if by_point.get(point) else None}
            for point in SATS_ASSESSMENT_POINTS
        },
        'latest_band': get_writing_band_label(latest_row.band) if latest_row and latest_row.band else '—',
    }


def get_latest_scaled_score(rows: list[SatsResult]) -> int | None:
    latest_row = max((row for row in rows if row.scaled_score is not None), key=lambda row: row.assessment_point, default=None)
    return latest_row.scaled_score if latest_row else None
