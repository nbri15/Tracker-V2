"""Assessment and dashboard service helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AssessmentSetting, Intervention, Pupil, SatsResult, SatsWritingResult, SchoolClass, SubjectResult, WritingResult

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


def compute_subject_result_values(setting: AssessmentSetting, paper_1_score: int | None, paper_2_score: int | None) -> dict:
    for label, score, max_score in (
        (setting.paper_1_name, paper_1_score, setting.paper_1_max),
        (setting.paper_2_name, paper_2_score, setting.paper_2_max),
    ):
        if score is None:
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
        computed = compute_subject_result_values(setting, result.paper_1_score, result.paper_2_score)
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


def _sort_rows_with_none_last(rows: list[dict], value_func, *, reverse: bool = False) -> list[dict]:
    populated = [row for row in rows if value_func(row) is not None]
    empty = [row for row in rows if value_func(row) is None]
    populated = sorted(populated, key=lambda row: (value_func(row), _name_sort_key(row)), reverse=reverse)
    empty = sorted(empty, key=_name_sort_key)
    return populated + empty


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
        return _sort_rows_with_none_last(rows, lambda row: row.get('paper_1_score'), reverse=reverse)
    if sort_column == 'paper_2_score':
        return _sort_rows_with_none_last(rows, lambda row: row.get('paper_2_score'), reverse=reverse)
    if sort_column == 'combined_score':
        return _sort_rows_with_none_last(rows, lambda row: row.get('combined_score'), reverse=reverse)
    if sort_column == 'combined_percent':
        return _sort_rows_with_none_last(rows, lambda row: row.get('combined_percent'), reverse=reverse)
    if sort_column == 'band_label':
        return _sort_rows_with_none_last(
            rows,
            lambda row: RESULT_THEME_ORDER.get(row.get('outcome_theme')),
            reverse=reverse,
        )
    return sorted(rows, key=_name_sort_key)


def sort_writing_result_rows(rows: list[dict], sort_column: str, sort_direction: str) -> list[dict]:
    reverse = sort_direction == 'desc'
    if sort_column == 'name':
        return sorted(rows, key=_name_sort_key, reverse=reverse)
    if sort_column == 'band_label':
        return _sort_rows_with_none_last(
            rows,
            lambda row: RESULT_THEME_ORDER.get(row.get('outcome_theme')),
            reverse=reverse,
        )
    if sort_column == 'notes':
        return _sort_rows_with_none_last(
            rows,
            lambda row: (row.get('notes') or '').strip().lower() or None,
            reverse=reverse,
        )
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
    for row in rows:
        if row.band_label in counts:
            counts[row.band_label] += 1
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
            SubjectResult.band_label.isnot(None),
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


def _build_recent_table_rows(school_class: SchoolClass, subject: str, academic_year: str) -> tuple[str, list[dict]]:
    latest_term = get_most_recent_term_with_data(school_class.id, subject, academic_year)
    if not latest_term:
        return 'No data', []

    if subject in CORE_SUBJECTS:
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
                'band_label': row.band_label,
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
            base_row.update({
                'paper_1_score': result.paper_1_score if result else None,
                'paper_2_score': result.paper_2_score if result else None,
                'combined_score': result.combined_score if result else None,
                'combined_percent': result.combined_percent if result else None,
                'band_label': result.band_label if result else None,
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
    pupils, pupil_rows = _build_class_detail_subject_rows(school_class, active_subject, active_term, academic_year, filters)
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
