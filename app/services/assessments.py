"""Assessment and dashboard service helpers."""

from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models import AssessmentSetting, SubjectResult, WritingResult

TERMS = [
    ('autumn', 'Autumn'),
    ('spring', 'Spring'),
    ('summer', 'Summer'),
]
TERM_SEQUENCE = {term: index for index, (term, _) in enumerate(TERMS, start=1)}
CORE_SUBJECTS = ('maths', 'reading', 'spag')
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

SUBJECT_DEFAULTS = {
    'maths': {
        'paper_1_name': 'Arithmetic',
        'paper_1_max': 40,
        'paper_2_name': 'Reasoning',
        'paper_2_max': 35,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 60.0,
        'exceeding_threshold_percent': 80.0,
    },
    'reading': {
        'paper_1_name': 'Paper 1',
        'paper_1_max': 30,
        'paper_2_name': 'Paper 2',
        'paper_2_max': 20,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 60.0,
        'exceeding_threshold_percent': 80.0,
    },
    'spag': {
        'paper_1_name': 'Spelling',
        'paper_1_max': 20,
        'paper_2_name': 'Grammar',
        'paper_2_max': 30,
        'below_are_threshold_percent': 45.0,
        'on_track_threshold_percent': 60.0,
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
    if today.month >= 1 and today.month < 4:
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

    combined_max = data.get('combined_max')
    calculated_combined = data['paper_1_max'] + data['paper_2_max']
    data['combined_max'] = combined_max or calculated_combined

    if data['paper_1_max'] < 0 or data['paper_2_max'] < 0 or data['combined_max'] <= 0:
        raise AssessmentValidationError('Max scores must be zero or above, and combined max must be greater than 0.')

    below = float(data['below_are_threshold_percent'])
    on_track = float(data['on_track_threshold_percent'])
    exceeding = float(data['exceeding_threshold_percent'])
    if not 0 <= below <= 100 or not 0 <= on_track <= 100 or not 0 <= exceeding <= 100:
        raise AssessmentValidationError('Threshold percentages must be between 0 and 100.')
    if below > on_track or on_track > exceeding:
        raise AssessmentValidationError('Thresholds must follow Below ≤ On Track ≤ Exceeding.')

    return data


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

    return get_or_create_assessment_setting(year_group=year_group, subject=subject, term=term)


def _round_percent(value: float) -> float:
    decimal_value = Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return float(decimal_value)


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
    }


def build_dashboard_summary(class_id: int | None, academic_year: str) -> list[dict]:
    """Build dashboard counts using the most recent available term per subject."""

    if not class_id:
        return [_empty_subject_summary(subject) for subject in (*CORE_SUBJECTS, 'writing')]

    rows: list[dict] = []
    for subject in CORE_SUBJECTS:
        subject_rows = (
            SubjectResult.query.join(SubjectResult.pupil)
            .filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.band_label.isnot(None),
                SubjectResult.pupil.has(class_id=class_id),
            )
            .all()
        )
        if not subject_rows:
            rows.append(_empty_subject_summary(subject))
            continue

        latest_term = max(subject_rows, key=lambda item: TERM_SEQUENCE.get(item.term, 0)).term
        latest_rows = [item for item in subject_rows if item.term == latest_term]
        counts = {'Working Towards': 0, 'On Track': 0, 'Exceeding': 0}
        for result in latest_rows:
            if result.band_label in counts:
                counts[result.band_label] += 1
        rows.append(
            {
                'subject': subject,
                'subject_label': format_subject_name(subject),
                'term': latest_term,
                'term_label': get_term_label(latest_term),
                'working_towards': counts['Working Towards'],
                'on_track': counts['On Track'],
                'exceeding': counts['Exceeding'],
                'on_track_plus': counts['On Track'] + counts['Exceeding'],
            }
        )

    writing_rows = (
        WritingResult.query.join(WritingResult.pupil)
        .filter(
            WritingResult.academic_year == academic_year,
            WritingResult.band.isnot(None),
            WritingResult.pupil.has(class_id=class_id),
        )
        .all()
    )
    if not writing_rows:
        rows.append(_empty_subject_summary('writing'))
        return rows

    latest_term = max(writing_rows, key=lambda item: TERM_SEQUENCE.get(item.term, 0)).term
    latest_rows = [item for item in writing_rows if item.term == latest_term]
    working_towards = sum(1 for item in latest_rows if item.band == 'working_towards')
    on_track = sum(1 for item in latest_rows if item.band == 'expected')
    exceeding = sum(1 for item in latest_rows if item.band == 'greater_depth')
    rows.append(
        {
            'subject': 'writing',
            'subject_label': format_subject_name('writing'),
            'term': latest_term,
            'term_label': get_term_label(latest_term),
            'working_towards': working_towards,
            'on_track': on_track,
            'exceeding': exceeding,
            'on_track_plus': on_track + exceeding,
        }
    )
    return rows
