"""Assessment and dashboard service helpers."""

from __future__ import annotations

from datetime import datetime, timezone

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
CLASS_DETAIL_TABS = ('overview', 'maths', 'reading', 'spag', 'writing', 'sats')
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
        'average_percent': None,
    }


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


def get_most_recent_term_with_data(class_id: int, subject: str, academic_year: str, subgroup: str = 'all') -> str | None:
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
    rows = apply_pupil_subgroup(query, subgroup).all()
    if not rows:
        return None
    return max(rows, key=lambda item: TERM_SEQUENCE.get(item.term, 0)).term


def compute_class_subject_summary(class_id: int, subject: str, academic_year: str, subgroup: str = 'all') -> dict:
    latest_term = get_most_recent_term_with_data(class_id, subject, academic_year, subgroup)
    if not latest_term:
        return _empty_subject_summary(subject)

    if subject in CORE_SUBJECTS:
        query = SubjectResult.query.join(SubjectResult.pupil).filter(
            SubjectResult.subject == subject,
            SubjectResult.academic_year == academic_year,
            SubjectResult.term == latest_term,
            Pupil.class_id == class_id,
        )
        latest_rows = apply_pupil_subgroup(query, subgroup).all()
        counts = _counts_from_band_labels(latest_rows)
        percents = [row.combined_percent for row in latest_rows if row.combined_percent is not None]
    else:
        query = WritingResult.query.join(WritingResult.pupil).filter(
            WritingResult.academic_year == academic_year,
            WritingResult.term == latest_term,
            Pupil.class_id == class_id,
        )
        latest_rows = apply_pupil_subgroup(query, subgroup).all()
        counts = _counts_from_writing_bands(latest_rows)
        percents = []

    return {
        'subject': subject,
        'subject_label': format_subject_name(subject),
        'term': latest_term,
        'term_label': get_term_label(latest_term),
        'working_towards': counts['Working Towards'],
        'on_track': counts['On Track'],
        'exceeding': counts['Exceeding'],
        'on_track_plus': counts['On Track'] + counts['Exceeding'],
        'pupil_count': len(latest_rows),
        'average_percent': round(sum(percents) / len(percents), 1) if percents else None,
    }


def build_dashboard_summary(class_id: int | None, academic_year: str, subgroup: str = 'all') -> list[dict]:
    if not class_id:
        return [_empty_subject_summary(subject) for subject in ALL_SUBJECTS]
    return [compute_class_subject_summary(class_id, subject, academic_year, subgroup) for subject in ALL_SUBJECTS]


def build_class_overview_row(school_class: SchoolClass, academic_year: str, subgroup: str = 'all') -> dict:
    pupil_query = school_class.pupils.filter_by(is_active=True)
    pupil_query = apply_pupil_subgroup(pupil_query, subgroup)
    pupil_count = pupil_query.count()
    subject_summaries = {subject: compute_class_subject_summary(school_class.id, subject, academic_year, subgroup) for subject in ALL_SUBJECTS}
    active_interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(Intervention.is_active.is_(True), Intervention.academic_year == academic_year, Pupil.class_id == school_class.id)
        .count()
    )
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
        card = _empty_subject_summary(subject)
        term_candidates = []
        for row in class_rows:
            summary = row['subjects'][subject]
            card['working_towards'] += summary['working_towards']
            card['on_track'] += summary['on_track']
            card['exceeding'] += summary['exceeding']
            card['on_track_plus'] += summary['on_track_plus']
            card['pupil_count'] += summary['pupil_count']
            if summary['term']:
                term_candidates.append(summary['term'])
        if term_candidates:
            latest_term = max(term_candidates, key=lambda item: TERM_SEQUENCE.get(item, 0))
            card['term'] = latest_term
            card['term_label'] = get_term_label(latest_term)
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


def _sort_class_detail_rows(rows: list[dict], sort_key: str) -> list[dict]:
    if sort_key == 'name_desc':
        return sorted(rows, key=lambda row: (row['pupil_name'].lower(),), reverse=True)
    if sort_key == 'percent_desc':
        return sorted(rows, key=lambda row: (row.get('combined_percent') is None, -(row.get('combined_percent') or 0), row['pupil_name'].lower()))
    if sort_key == 'percent_asc':
        return sorted(rows, key=lambda row: (row.get('combined_percent') is None, row.get('combined_percent') or 0, row['pupil_name'].lower()))
    if sort_key == 'band_asc':
        return sorted(rows, key=lambda row: ((row.get('band_label') or 'ZZZ'), row['pupil_name'].lower()))
    return sorted(rows, key=lambda row: row['pupil_name'].lower())


def build_class_subject_table(school_class: SchoolClass, subject: str, academic_year: str, *, term: str = '', search: str = '', sort: str = 'name_asc') -> dict:
    selected_term = term.strip()
    latest_term = get_most_recent_term_with_data(school_class.id, subject, academic_year)
    effective_term = selected_term or latest_term

    term_options = [{'value': value, 'label': label} for value, label in TERMS]
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    if not effective_term:
        return {
            'subject': subject,
            'subject_label': format_subject_name(subject),
            'rows': _sort_class_detail_rows(
                [
                    {
                        'pupil_name': pupil.full_name,
                        'paper_1_score': None,
                        'paper_2_score': None,
                        'combined_score': None,
                        'combined_percent': None,
                        'band_label': None,
                        'source': None,
                    }
                    for pupil in pupils
                    if not search.lower().strip() or search.lower().strip() in pupil.full_name.lower()
                ],
                sort,
            ) if subject in CORE_SUBJECTS else _sort_class_detail_rows(
                [
                    {'pupil_name': pupil.full_name, 'band_label': None, 'notes': None}
                    for pupil in pupils
                    if not search.lower().strip() or search.lower().strip() in pupil.full_name.lower()
                ],
                sort,
            ),
            'term': selected_term,
            'effective_term': None,
            'term_label': 'No data',
            'latest_term': latest_term,
            'paper_1_label': 'Paper 1',
            'paper_2_label': 'Paper 2',
            'term_options': term_options,
        }

    search_value = search.lower().strip()

    if subject in CORE_SUBJECTS:
        setting = get_subject_setting(school_class.year_group, subject, effective_term)
        query = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.term == effective_term,
                Pupil.class_id == school_class.id,
            )
            .order_by(Pupil.last_name, Pupil.first_name)
        )
        results = {row.pupil_id: row for row in query.all()}
        rows = []
        for pupil in pupils:
            row = results.get(pupil.id)
            if search_value and search_value not in pupil.full_name.lower():
                continue
            rows.append(
                {
                    'pupil_name': pupil.full_name,
                    'paper_1_score': row.paper_1_score if row else None,
                    'paper_2_score': row.paper_2_score if row else None,
                    'combined_score': row.combined_score if row else None,
                    'combined_percent': row.combined_percent if row else None,
                    'band_label': row.band_label if row else None,
                    'source': row.source if row else None,
                }
            )
        rows = _sort_class_detail_rows(rows, sort)
        return {
            'subject': subject,
            'subject_label': format_subject_name(subject),
            'rows': rows,
            'term': selected_term,
            'effective_term': effective_term,
            'term_label': get_term_label(effective_term),
            'latest_term': latest_term,
            'paper_1_label': setting.paper_1_name,
            'paper_2_label': setting.paper_2_name,
            'term_options': term_options,
        }

    results = (
        WritingResult.query.join(WritingResult.pupil)
        .filter(
            WritingResult.academic_year == academic_year,
            WritingResult.term == effective_term,
            Pupil.class_id == school_class.id,
        )
        .order_by(Pupil.last_name, Pupil.first_name)
        .all()
    )
    results_by_pupil = {row.pupil_id: row for row in results}
    rows = []
    for pupil in pupils:
        if search_value and search_value not in pupil.full_name.lower():
            continue
        row = results_by_pupil.get(pupil.id)
        rows.append(
            {
                'pupil_name': pupil.full_name,
                'band_label': get_writing_band_label(row.band) if row else None,
                'notes': row.notes if row else None,
            }
        )
    rows = _sort_class_detail_rows(rows, sort)
    return {
        'subject': subject,
        'subject_label': format_subject_name(subject),
        'rows': rows,
        'term': selected_term,
        'effective_term': effective_term,
        'term_label': get_term_label(effective_term),
        'latest_term': latest_term,
        'paper_1_label': None,
        'paper_2_label': None,
        'term_options': term_options,
    }


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


def get_class_detail_context(school_class: SchoolClass, academic_year: str, *, active_tab: str = 'overview', term: str = '', search: str = '', sort: str = 'name_asc') -> dict:
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    summary_rows = build_dashboard_summary(school_class.id, academic_year)
    subject_tables = {
        subject: build_class_subject_table(school_class, subject, academic_year, term=term, search=search, sort=sort)
        for subject in ALL_SUBJECTS
    }

    interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(Intervention.academic_year == academic_year, Pupil.class_id == school_class.id)
        .order_by(Intervention.is_active.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )
    sats_summary = build_year6_sats_summary(school_class, academic_year)
    active_interventions = sum(1 for record in interventions if record.is_active)
    tabs = [{'key': 'overview', 'label': 'Overview'}]
    tabs.extend({'key': subject, 'label': format_subject_name(subject)} for subject in ALL_SUBJECTS)
    if sats_summary:
        tabs.append({'key': 'sats', 'label': 'SATs'})
    valid_tab_keys = {item['key'] for item in tabs}
    if active_tab not in valid_tab_keys:
        active_tab = 'overview'
    active_subject_table = subject_tables.get(active_tab) if active_tab in ALL_SUBJECTS else None
    overview_cards = [
        {'label': 'Class', 'value': school_class.name, 'muted': f'Year {school_class.year_group}'},
        {'label': 'Teacher', 'value': school_class.teacher.username if school_class.teacher else 'Unassigned', 'muted': 'Assigned lead'},
        {'label': 'Pupils', 'value': len(pupils), 'muted': 'Active on roll'},
        {'label': 'Interventions', 'value': active_interventions, 'muted': f'{academic_year} active'},
    ]

    return {
        'school_class': school_class,
        'pupils': pupils,
        'summary_rows': summary_rows,
        'subject_tables': subject_tables,
        'active_subject_table': active_subject_table,
        'interventions': interventions,
        'sats_summary': sats_summary,
        'active_interventions': active_interventions,
        'active_tab': active_tab,
        'tabs': tabs,
        'search': search,
        'sort': sort,
        'term': term,
        'overview_cards': overview_cards,
    }


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
