Warning: truncated output (original token count: 19272)
Total output lines: 1910

"""Assessment and dashboard service helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import has_request_context, request, session
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    AcademicYear,
    AssessmentSetting,
    FoundationResult,
    Intervention,
    PhonicsScore,
    PhonicsTestColumn,
    Pupil,
    PupilClassHistory,
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
from app.services.gender import CANONICAL_GENDERS, gender_filter_clause, normalize_gender
from app.utils import current_school_id, school_scoped_query

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
    'send': 'SEND',
}
BOOLEAN_FILTER_CHOICES = {
    'all': 'All',
    'yes': 'Yes',
    'no': 'No',
}
SATS_SUBJECTS = ('reading', 'maths', 'spag')
SATS_ASSESSMENT_POINTS = (1, 2, 3, 4)


@dataclass(frozen=True)
class AcademicYearOption:
    id: int | str
    name: str

    @property
    def label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self.name == other
        return super().__eq__(other)


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




def short_band_label(value: str | None) -> str:
    if value is None:
        return '—'
    text = str(value).strip()
    if not text:
        return '—'

    normalized = text.lower().replace('_', ' ')

    if normalized in {'working towards', 'wt', 'wts', 'below', 'not on track'}:
        return 'WT'
    if normalized in {'expected', 'on track', 'working at', 'ot'}:
        return 'OT'
    if normalized in {'exs', 'exc', 'exceeding', 'exceed', 'greater depth', 'gds'}:
        return 'EXC'

    if any(token in normalized for token in ('working towards', 'towards')):
        return 'WT'
    if any(token in normalized for token in ('on track', 'expected', 'working at')):
        return 'OT'
    if any(token in normalized for token in ('exceeding', 'exceed', 'greater depth', 'gds', 'exs', 'exc')):
        return 'EXC'
    return text


def display_band_short(value: str | None) -> str:
    return short_band_label(value)


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


def is_academic_year_rollover_due(working_year: str, calendar_year: str | None = None) -> bool:
    """Return true only when the calendar has advanced beyond the working year."""
    calendar_year = calendar_year or get_current_academic_year()
    try:
        return int(calendar_year.split('/')[0]) > int(working_year.split('/')[0])
    except (AttributeError, TypeError, ValueError):
        return False


def get_current_term(today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    if today.month >= 9:
        return 'autumn'
    if 1 <= today.month < 4:
        return 'spring'
    return 'summer'


def build_academic_year_options(current_year: str | None = None, total_years: int = 4) -> list:
    """Return AcademicYear rows for selectors, falling back to generated names."""
    rows = AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    if rows:
        return [AcademicYearOption(row.id, row.name) for row in rows]
    current_year = current_year or get_current_academic_year()
    start_year = int(current_year.split('/')[0])
    years = [f'{year}/{str(year + 1)[-2:]}' for year in range(start_year - 1, start_year - 1 + total_years)]
    if current_year not in years:
        years.append(current_year)
    return [AcademicYearOption(name, name) for name in sorted(set(years), reverse=True)]


def get_selected_academic_year(raw_year_id: str | None = None, raw_academic_year: str | None = None) -> AcademicYear:
    """Resolve and persist the selected academic year for the current request.

    Priority: explicit query/form year, session selection, school/global current year,
    then latest available academic year. `year` is treated as an AcademicYear id;
    `academic_year` is kept for legacy links that pass the display name.
    """
    selected = None
    explicit_selection = False

    if has_request_context():
        raw_year_id = raw_year_id or request.values.get('year') or request.values.get('academic_year_id')
        raw_academic_year = raw_academic_year or request.values.get('academic_year')

    if raw_year_id:
        try:
            selected = AcademicYear.query.get(int(raw_year_id))
            explicit_selection = selected is not None
        except (TypeError, ValueError):
            selected = None
    if selected is None and raw_academic_year:
        selected = AcademicYear.query.filter_by(name=raw_academic_year).first()
        explicit_selection = selected is not None

    if selected is None and has_request_context():
        session_year_id = session.get('selected_academic_year_id')
        if session_year_id:
            try:
                selected = AcademicYear.query.get(int(session_year_id))
            except (TypeError, ValueError):
                selected = None

    if selected is None and has_request_context():
        school_id = current_school_id()
        if school_id is not None:
            selected = get_school_working_academic_year(school_id)
    if selected is None:
        selected = AcademicYear.query.filter_by(is_current=True).order_by(AcademicYear.name.desc()).first()
    if selected is None:
        selected = AcademicYear.query.order_by(AcademicYear.name.desc()).first()
    if selected is None:
        selected = AcademicYear(name=get_current_academic_year(), is_current=True)

    if has_request_context() and (explicit_selection or not session.get('selected_academic_year_id')) and getattr(selected, 'id', None):
        session['selected_academic_year_id'] = selected.id
    return selected




def get_selected_current_academic_year() -> str:
    """Return the request school's working year, with a legacy global fallback."""

    if has_request_context():
        school_id = current_school_id()
        if school_id is not None:
            return get_school_working_academic_year(school_id).name

    current = AcademicYear.query.filter_by(is_current=True).order_by(AcademicYear.name.desc()).first()
    return current.name if current else get_current_academic_year()


def get_school_working_academic_year(school_id: int | None) -> AcademicYear:
    """Resolve a school's operational year without consulting the viewing session.

    A school's explicit setting is authoritative. The legacy global current flag is
    retained as a migration fallback, followed by the calendar-derived year. In
    particular, the newest database row and dashboard/report selection are never
    treated as the school's working year.
    """
    from app.models import School

    school = db.session.get(School, school_id) if school_id is not None else None
    if school and school.current_academic_year:
        return school.current_academic_year

    current = AcademicYear.query.filter_by(is_current=True).order_by(AcademicYear.name.desc()).first()
    if current:
        return current

    fallback_name = get_current_academic_year()
    fallback = AcademicYear.query.filter_by(name=fallback_name).first()
    return fallback or AcademicYear(name=fallback_name, is_current=False)


def is_current_academic_year(academic_year: str | None) -> bool:
    return (academic_year or get_selected_current_academic_year()) == get_selected_current_academic_year()


def get_class_pupil_query(school_class: SchoolClass, academic_year: str | None = None):
    """Return pupils belonging to a class in the selected academic year.

    Current-year views use the pupil's live class assignment. Historical views use
    PupilClassHistory so a later promotion or import does not move past records.
    """

    current_membership_query = Pupil.query.filter(
        Pupil.class_id == school_class.id,
        Pupil.school_id == school_class.school_id,
    )
    if not academic_year or is_current_academic_year(academic_year):
        return current_membership_query

    history_exists = PupilClassHistory.query.filter(
        PupilClassHistory.school_id == school_class.school_id,
        PupilClassHistory.academic_year == academic_year,
        PupilClassHistory.class_name == school_class.name,
        PupilClassHistory.year_group == school_class.year_group,
    ).first() is not None
    if not history_exists:
        return current_membership_query

    return (
        Pupil.query
        .join(PupilClassHistory, PupilClassHistory.pupil_id == Pupil.id)
        .filter(
            PupilClassHistory.school_id == school_class.school_id,
            PupilClassHistory.academic_year == academic_year,
            PupilClassHistory.class_name == school_class.name,
            PupilClassHistory.year_group == school_class.year_group,
            Pupil.school_id == school_class.school_id,
        )
    )


def get_class_pupil_ids(school_class: SchoolClass, academic_year: str | None = None, filters: dict | None = None, subgroup: str = 'all') -> list[int]:
    query = get_class_pupil_query(school_class, academic_year)
    query = apply_pupil_filters(query, subgroup=subgroup, filters=filters)
    return [pupil.id for pupil in query.all()]


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
    rounded = round(delta, 1)
    if rounded == 0:
        return '→ 0'
    formatted = f'{rounded:.1f}'.rstrip('0').rstrip('.')
    if rounded > 0:
        return f'↑ +{formatted}'
    if rounded < 0:
        return f'↓ {formatted}'
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
    mapping = {
        'spring': 'autumn',
        'summer': 'spring',
    }
    return mapping.get((term or '').strip().lower())


def get_latest_previous_assessment(
    pupil_id: int,
    subject: str,
    current_term: str,
    academic_year: str,
) -> str | None:
    normalized_subject = (subject or '').strip().lower()
    normalized_term = (current_term or '').strip().lower()
    invalid_values = {'', 'not_assessed', 'not assessed'}
    orders = (
        ['autumn', 'spring', 'summer'],
        ['autumn_1', 'autumn_2', 'spring_1', 'spring_2', 'summer_1', 'summer_2'],
    )
    sequence = next((order for order in orders if normalized_term in order), None)
    if not sequence:
        return None
    current_index = sequence.index(normalized_term)
    if current_index <= 0:
        return None
    lookback_terms = list(reversed(sequence[:current_index]))

    if normalized_subject == 'writing':
        prior_rows = WritingResult.query.filter(
            WritingResult.pupil_id == pupil_id,
            WritingResult.academic_year == academic_year,
            WritingResult.term.in_(lookback_terms),
        ).all()
        by_term = {(row.term or '').strip().lower(): row.band for row in prior_rows}
    else:
        prior_rows = FoundationResult.query.filter(
            FoundationResult.pupil_id == pupil_id,
            FoundationResult.academic_year == academic_year,
            FoundationResult.subject == normalized_subject,
            FoundationResult.half_term.in_(lookback_terms),
        ).all()
        by_term = {(row.half_term or '').strip().lower(): row.judgement for row in prior_rows}

    for term in lookback_terms:
        value = by_term.get(term)
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned.lower() in invalid_values:
            continue
        return cleaned
    return None


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




def pupil_send_value(pupil: Pupil) -> bool | None:
    profile = getattr(pupil, 'profile', None)
    profile_send = getattr(profile, 'send', None) if profile is not None else None
    if pupil.send is True or profile_send is True:
        return True
    if pupil.send is False and profile_send in (False, None):
        return False
    if pupil.send is None and profile_send is False:
        return False
    return None


def pupil_has_send(pupil: Pupil) -> bool:
    return pupil_send_value(pupil) is True

def apply_pupil_subgroup(query, subgroup: str):
    if subgroup == 'pp':
        return query.filter(Pupil.pupil_premium.is_(True))
    if subgroup == 'laps':
        return query.filter(Pupil.laps.is_(True))
    if subgroup == 'service_child':
        return query.filter(Pupil.service_child.is_(True))
    if subgroup == 'send':
        return query.filter(Pupil.send.is_(True))
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
        clause = gender_filter_clause(gender)
        if clause is not None:
            query = query.filter(clause)

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

    send_value = (filters.get('send') or '').strip()
    if send_value == 'yes':
        query = query.filter(Pupil.send.is_(True))
    elif send_value == 'no':
        query = query.filter(Pupil.send.is_(False))

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
        'send': (args…7272 tokens truncated…3)', 'exceeding': 'Exceeding (34+)'}
        rows = []
        for year in years:
            pupils_query = scoped_class_filter(Pupil.query.join(Pupil.school_class)).filter(SchoolClass.year_group == year)
            pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
            pupils = pupils_query.all()
            included_pupil_ids.update(pupil.id for pupil in pupils)
            pupil_ids = [pupil.id for pupil in pupils]
            year_columns = [column for column in columns if column.year_group == year]
            target_column = selected_column if selected_column and selected_column.year_group == year else (year_columns[-1] if year_columns else None)
            counts = {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0}
            if target_column and pupil_ids:
                scores = PhonicsScore.query.filter_by(academic_year=academic_year, phonics_test_column_id=target_column.id).filter(PhonicsScore.pupil_id.in_(pupil_ids)).all()
                included_result_count += len(scores)
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
        return finalize_with_debug(_finalize_headline_payload(
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
        ) | {'selected_tracker_key': bucket_key})

    if subject == 'times_tables':
        years = [4]
        columns = (
            scoped_model_filter(TimesTableTestColumn.query, TimesTableTestColumn).filter_by(year_group=4, is_active=True)
            .order_by(TimesTableTestColumn.display_order, TimesTableTestColumn.id)
            .all()
        )
        selected_column = next((column for column in columns if str(column.id) == str(tracker_key)), None) if tracker_key else None
        target_column = selected_column or (columns[-1] if columns else None)
        bucket_key = str(target_column.id) if target_column else 'latest'
        bucket_labels = {bucket_key: target_column.name if target_column else 'Latest test'}
        band_labels = {'working_towards': 'Working Towards (<20)', 'on_track_plus': 'On Track+ (20-24)', 'exceeding': 'Exceeding (25)'}

        pupils_query = scoped_class_filter(Pupil.query.join(Pupil.school_class)).filter(SchoolClass.year_group == 4)
        pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
        pupils = pupils_query.all()
        included_pupil_ids.update(pupil.id for pupil in pupils)
        pupil_ids = [pupil.id for pupil in pupils]
        counts = {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0}
        if target_column and pupil_ids:
            scores = TimesTableScore.query.filter_by(academic_year=academic_year, times_table_test_column_id=target_column.id).filter(TimesTableScore.pupil_id.in_(pupil_ids)).all()
            included_result_count += len(scores)
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
        return finalize_with_debug(_finalize_headline_payload(
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
        ) | {'selected_tracker_key': bucket_key})

    # SATs (Year 6 scaled score headlines).
    tabs = (
        scoped_model_filter(SatsExamTab.query.filter_by(year_group=6), SatsExamTab)
        .order_by(SatsExamTab.display_order, SatsExamTab.id)
        .all()
    )
    selected_tab = next((tab for tab in tabs if str(tab.id) == str(tracker_key)), None) if tracker_key else None
    if not selected_tab:
        selected_tab = next((tab for tab in tabs if tab.is_active), tabs[-1] if tabs else None)
    scaled_columns = []
    if selected_tab:
        scaled_columns = (
            scoped_model_filter(
                SatsColumnSetting.query.filter_by(year_group=6, exam_tab_id=selected_tab.id, score_type='scaled', is_active=True),
                SatsColumnSetting,
            )
            .filter(SatsColumnSetting.column_key.in_(['maths_scaled', 'reading_scaled', 'spag_scaled']))
            .order_by(SatsColumnSetting.display_order, SatsColumnSetting.id)
            .all()
        )
    pupils_query = scoped_class_filter(Pupil.query.join(Pupil.school_class)).filter(SchoolClass.year_group == 6)
    pupils_query = apply_pupil_filters(pupils_query, subgroup=subgroup, filters=filters)
    pupils = pupils_query.all()
    included_pupil_ids.update(pupil.id for pupil in pupils)
    pupil_ids = [pupil.id for pupil in pupils]
    measure_labels = {'working_towards': 'Working Towards (<100)', 'on_track_plus': 'On Track+ (100-109)', 'exceeding': 'Exceeding (110+)'}
    bucket_keys = [column.column_key for column in scaled_columns] or ['maths_scaled', 'reading_scaled', 'spag_scaled']
    bucket_labels = {'maths_scaled': 'Maths scaled', 'reading_scaled': 'Reading scaled', 'spag_scaled': 'SPaG scaled'}
    bucket_totals = {bucket: {'total': 0, 'working_towards': 0, 'on_track_plus': 0, 'exceeding': 0} for bucket in bucket_keys}
    if pupil_ids and scaled_columns:
        results = (
            scoped_model_filter(SatsColumnResult.query.filter_by(academic_year=academic_year), SatsColumnResult)
            .filter(SatsColumnResult.pupil_id.in_(pupil_ids), SatsColumnResult.column_id.in_([column.id for column in scaled_columns]))
            .all()
        )
        included_result_count += len(results)
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
    return finalize_with_debug(_finalize_headline_payload(
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
    ) | {'selected_tracker_key': str(selected_tab.id) if selected_tab else ''})


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
    if pupil_has_send(pupil):
        flags.append('SEND')
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
        get_class_pupil_query(school_class, academic_year),
        filters,
    ).order_by(Pupil.last_name, Pupil.first_name).all()

    pupil_ids = [pupil.id for pupil in pupils]
    if subject in CORE_SUBJECTS:
        setting = get_subject_setting(school_class.year_group, subject, term)
        prev_term = previous_term(term)
        result_rows = SubjectResult.query.filter(
            SubjectResult.subject == subject,
            SubjectResult.academic_year == academic_year,
            SubjectResult.term == term,
            SubjectResult.pupil_id.in_(pupil_ids or [0]),
        ).all()
        result_lookup = {row.pupil_id: row for row in result_rows}
        previous_lookup: dict[int, SubjectResult] = {}
        if prev_term:
            previous_rows = SubjectResult.query.filter(
                SubjectResult.subject == subject,
                SubjectResult.academic_year == academic_year,
                SubjectResult.term == prev_term,
                SubjectResult.pupil_id.in_(pupil_ids or [0]),
            ).all()
            previous_lookup = {row.pupil_id: row for row in previous_rows}
    else:
        result_rows = WritingResult.query.filter(
            WritingResult.academic_year == academic_year,
            WritingResult.term == term,
            WritingResult.pupil_id.in_(pupil_ids or [0]),
        ).all()
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
            'send': pupil.send,
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
        get_class_pupil_query(school_class, academic_year),
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
            'send': pupil.send,
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

    pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).order_by(Pupil.last_name, Pupil.first_name).all()
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
        get_class_pupil_query(school_class, academic_year),
        filters,
    ).order_by(Pupil.last_name, Pupil.first_name).all()

    context = {
        'school_class': school_class,
        'available_subjects': available_subjects,
        'selected_subject': active_subject,
        'available_terms': TERMS,
        'selected_term': None,
        'filtered_pupil_count': len(filtered_pupils),
        'total_pupil_count': get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).count(),
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


def get_latest_result(results: list, *, key: str = 'assessment_point'):
    """Return the newest result-like object in a list using a safe key."""
    if not results:
        return None
    return max(results, key=lambda row: getattr(row, key, 0) or 0, default=None)


def calculate_band(combined_percent: float | None, below_threshold: float = 45.0, exceeding_threshold: float = 80.0) -> str:
    return SubjectResult.calculate_band_label(combined_percent, below_threshold, exceeding_threshold)


def calculate_progress(current: float | int | None, previous: float | int | None) -> dict[str, float | int | str | None]:
    if current is None or previous is None:
        return {'delta': None, 'label': '—', 'theme': None}
    delta = current - previous
    return {'delta': delta, 'label': format_progress_delta(delta), 'theme': progress_theme(delta)}


def get_term_filtered_results(query, term: str | None = None):
    normalized = (term or '').strip().lower()
    if normalized and normalized != 'all':
        return query.filter_by(term=normalized)
    return query


def get_tracker_results(pupil_id: int, academic_year: str, *, term: str | None = None) -> list[SubjectResult]:
    query = SubjectResult.query.filter_by(pupil_id=pupil_id, academic_year=academic_year)
    query = get_term_filtered_results(query, term)
    return query.order_by(SubjectResult.subject, SubjectResult.term).all()


def get_subject_summary(pupil_id: int, academic_year: str, subject: str, *, term: str | None = None) -> dict:
    rows = get_tracker_results(pupil_id, academic_year, term=term)
    subject_rows = [row for row in rows if row.subject == subject]
    latest = get_latest_result(subject_rows)
    previous_rows = [row for row in subject_rows if latest is None or row.assessment_point != latest.assessment_point]
    previous = get_latest_result(previous_rows)
    progress = calculate_progress(
        latest.combined_percent if latest else None,
        previous.combined_percent if previous else None,
    )
    return {
        'subject': subject,
        'count': len(subject_rows),
        'latest': latest,
        'previous': previous,
        'progress': progress,
    }


def get_dashboard_stats(class_id: int | None, academic_year: str) -> list[dict]:
    return build_dashboard_summary(class_id, academic_year)
