"""Assessment and dashboard service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AssessmentSetting, Pupil, SchoolClass, SubjectResult, WritingResult

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
CLASS_SORT_OPTIONS = {
    'year_group': 'Year group',
    'class_name': 'Class name',
    'pupil_count_desc': 'Pupil count (high to low)',
    'pupil_count_asc': 'Pupil count (low to high)',
}

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


def format_subject_name(subject: str) -> str:
    """Return a user-facing subject label."""

    return SUBJECT_DISPLAY_NAMES.get(subject, subject.replace('_', ' ').title())


def get_term_label(term: str) -> str:
    """Return a user-facing term label."""

    return dict(TERMS).get(term, term.title())


def get_writing_band_label(band: str | None) -> str:
    """Return a user-facing writing band label."""

    if not band:
        return '—'
    return WRITING_BAND_LABELS.get(band, band.replace('_', ' ').title())


def get_current_academic_year(today: datetime | None = None) -> str:
    """Return the current academic year in UK format, e.g. 2025/26."""

    today = today or datetime.now(UTC)
    year = today.year
    start_year = year if today.month >= 9 else year - 1
    return f'{start_year}/{str(start_year + 1)[-2:]}'


def get_current_term(today: datetime | None = None) -> str:
    """Return the current school term based on today's month."""

    today = today or datetime.now(UTC)
    if today.month >= 9:
        return 'autumn'
    if 1 <= today.month < 4:
        return 'spring'
    return 'summer'


def build_academic_year_options(current_year: str, total_years: int = 4) -> list[str]:
    """Build a small list of academic year options around the current year."""

    start_year = int(current_year.split('/')[0])
    years = [f'{year}/{str(year + 1)[-2:]}' for year in range(start_year - 1, start_year - 1 + total_years)]
    if current_year not in years:
        years.append(current_year)
    return sorted(set(years), reverse=True)


def get_setting_defaults(subject: str) -> dict:
    """Return default editable settings for a subject."""

    defaults = SUBJECT_DEFAULTS[subject].copy()
    defaults['combined_max'] = defaults['paper_1_max'] + defaults['paper_2_max']
    return defaults


def validate_setting_payload(data: dict) -> dict:
    """Validate and normalize assessment setting values."""

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
    """Fetch or create an assessment setting row."""

    setting = AssessmentSetting.query.filter_by(year_group=year_group, subject=subject, term=term).first()
    if setting:
        return setting

    defaults = get_setting_defaults(subject)
    setting = AssessmentSetting(year_group=year_group, subject=subject, term=term, **defaults)
    db.session.add(setting)
    db.session.flush()
    return setting


def get_subject_setting(year_group: int, subject: str, term: str) -> AssessmentSetting:
    """Return the saved setting or a generated default row."""

    return get_or_create_assessment_setting(year_group, subject, term)


def update_assessment_setting(setting: AssessmentSetting, payload: dict) -> AssessmentSetting:
    """Apply a validated payload to an assessment setting row."""

    for field, value in payload.items():
        setattr(setting, field, value)
    db.session.add(setting)
    return setting


def compute_subject_result_values(setting: AssessmentSetting, paper_1_score: int | None, paper_2_score: int | None) -> dict:
    """Compute combined score, percent, and band label for a subject result."""

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
    band_label = SubjectResult.calculate_band_label(
        combined_percent,
        setting.below_are_threshold_percent,
        setting.exceeding_threshold_percent,
    )
    return {
        'combined_score': combined_score,
        'combined_percent': combined_percent,
        'band_label': band_label,
    }


def recalculate_subject_results_for_scope(
    year_group: int,
    subject: str,
    term: str,
    *,
    academic_year: str | None = None,
    class_id: int | None = None,
) -> int:
    """Recalculate derived result fields after a setting change."""

    setting = get_subject_setting(year_group, subject, term)
    query = (
        SubjectResult.query.join(SubjectResult.pupil).join(Pupil.school_class)
        .options(joinedload(SubjectResult.pupil).joinedload(Pupil.school_class))
        .filter(
            SubjectResult.subject == subject,
            SubjectResult.term == term,
            SchoolClass.year_group == year_group,
        )
    )
    if academic_year:
        query = query.filter(SubjectResult.academic_year == academic_year)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)

    results = query.all()
    for result in results:
        computed = compute_subject_result_values(setting, result.paper_1_score, result.paper_2_score)
        result.combined_score = computed['combined_score']
        result.combined_percent = computed['combined_percent']
        result.band_label = computed['band_label']
        db.session.add(result)
    return len(results)


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


def get_most_recent_term_with_data(class_id: int, subject: str, academic_year: str) -> str | None:
    """Return the latest term with saved data for a class and subject."""

    if subject in CORE_SUBJECTS:
        rows = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.band_label.isnot(None),
                Pupil.class_id == class_id,
            )
            .all()
        )
    else:
        rows = (
            WritingResult.query.join(WritingResult.pupil)
            .filter(
                WritingResult.academic_year == academic_year,
                WritingResult.band.isnot(None),
                Pupil.class_id == class_id,
            )
            .all()
        )

    if not rows:
        return None
    return max(rows, key=lambda item: TERM_SEQUENCE.get(item.term, 0)).term


def compute_class_subject_summary(class_id: int, subject: str, academic_year: str) -> dict:
    """Build a subject summary for a single class using the most recent saved term."""

    latest_term = get_most_recent_term_with_data(class_id, subject, academic_year)
    if not latest_term:
        return _empty_subject_summary(subject)

    if subject in CORE_SUBJECTS:
        latest_rows = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.term == latest_term,
                Pupil.class_id == class_id,
            )
            .all()
        )
        counts = _counts_from_band_labels(latest_rows)
    else:
        latest_rows = (
            WritingResult.query.join(WritingResult.pupil)
            .filter(
                WritingResult.academic_year == academic_year,
                WritingResult.term == latest_term,
                Pupil.class_id == class_id,
            )
            .all()
        )
        counts = _counts_from_writing_bands(latest_rows)

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
    }


def build_dashboard_summary(class_id: int | None, academic_year: str) -> list[dict]:
    """Build dashboard counts using the most recent available term per subject."""

    if not class_id:
        return [_empty_subject_summary(subject) for subject in ALL_SUBJECTS]
    return [compute_class_subject_summary(class_id, subject, academic_year) for subject in ALL_SUBJECTS]


def build_class_overview_row(school_class: SchoolClass, academic_year: str) -> dict:
    """Build a dashboard row for a class."""

    pupil_count = school_class.pupils.filter_by(is_active=True).count()
    subject_summaries = {
        subject: compute_class_subject_summary(school_class.id, subject, academic_year)
        for subject in ALL_SUBJECTS
    }
    return {
        'class': school_class,
        'class_id': school_class.id,
        'class_name': school_class.name,
        'year_group': school_class.year_group,
        'teacher_name': school_class.teacher.username if school_class.teacher else 'Unassigned',
        'pupil_count': pupil_count,
        'subjects': subject_summaries,
    }


def build_subject_overview_cards(class_rows: list[dict]) -> list[dict]:
    """Aggregate subject summary counts across class rows."""

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
            card['pupil_count'] += row['pupil_count']
            if summary['term']:
                term_candidates.append(summary['term'])
        if term_candidates:
            latest_term = max(term_candidates, key=lambda item: TERM_SEQUENCE.get(item, 0))
            card['term'] = latest_term
            card['term_label'] = get_term_label(latest_term)
        cards.append(card)
    return cards


def get_class_detail_context(school_class: SchoolClass, academic_year: str) -> dict:
    """Return summary and recent result context for a single class."""

    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    summary_rows = build_dashboard_summary(school_class.id, academic_year)
    recent_tables: list[dict] = []

    for subject in ALL_SUBJECTS:
        latest_term = get_most_recent_term_with_data(school_class.id, subject, academic_year)
        if not latest_term:
            recent_tables.append(
                {
                    'subject': subject,
                    'subject_label': format_subject_name(subject),
                    'term_label': 'No data',
                    'rows': [],
                }
            )
            continue

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

        recent_tables.append(
            {
                'subject': subject,
                'subject_label': format_subject_name(subject),
                'term_label': get_term_label(latest_term),
                'rows': formatted_rows,
            }
        )

    return {
        'school_class': school_class,
        'pupils': pupils,
        'summary_rows': summary_rows,
        'recent_tables': recent_tables,
    }
