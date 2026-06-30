"""CSV parsing, validation, import, and export helpers."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from sqlalchemy import or_
from flask_login import current_user

from app.extensions import db
from app.models import (
    Intervention,
    Pupil,
    PupilClassHistory,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SatsColumnSetting,
    SatsExamTab,
    SatsResult,
    PhonicsScore,
    PhonicsTestColumn,
    SchoolClass,
    SimpleSatsExamTab,
    SubjectResult,
    TimesTableScore,
    TimesTableTestColumn,
    FoundationResult,
    WritingResult,
)
from app.utils import current_school_id, school_scoped_query
from .assessments import get_selected_current_academic_year
from .setup import get_or_create_academic_year
from .assessments import CsvImportError, WRITING_BAND_LABELS, build_class_overview_row, compute_subject_result_values, get_subject_setting, short_band_label
from .reception import RECEPTION_STATUS_CHOICES, RECEPTION_TRACKING_POINTS, RECEPTION_YEAR_GROUP
from .pupil_overview import build_pupil_overview_data, summarize_gld_status
from .sats_tracker import CALCULATION_KEY_MAP, build_sats_tracker_rows, get_sats_columns, get_sats_exam_tabs
from .gender import normalize_gender

COMBINED_PUPIL_COLUMNS = [
    'pupil',
    'class_name',
    'year_group',
    'academic_year',
    'gender',
    'pupil_premium',
    'send',
    'laps',
    'service_child',
]
# Backwards-compatible columns accepted on upload, but not prioritised in the template.
COMBINED_LEGACY_PUPIL_COLUMNS = ['first_name', 'last_name']
COMBINED_SUBJECT_SCORE_COLUMNS = {
    'maths': {
        'autumn': ('maths_autumn_paper1', 'maths_autumn_paper2'),
        'spring': ('maths_spring_paper1', 'maths_spring_paper2'),
        'summer': ('maths_summer_paper1', 'maths_summer_paper2'),
    },
    'reading': {
        'autumn': ('reading_autumn_paper1', 'reading_autumn_paper2'),
        'spring': ('reading_spring_paper1', 'reading_spring_paper2'),
        'summer': ('reading_summer_paper1', 'reading_summer_paper2'),
    },
    'spag': {
        'autumn': ('spag_autumn_paper1', 'spag_autumn_paper2'),
        'spring': ('spag_spring_paper1', 'spag_spring_paper2'),
        'summer': ('spag_summer_paper1', 'spag_summer_paper2'),
    },
}
COMBINED_WRITING_COLUMNS = {
    'autumn': ('writing_autumn_band', 'writing_autumn_notes'),
    'spring': ('writing_spring_band', 'writing_spring_notes'),
    'summer': ('writing_summer_band', 'writing_summer_notes'),
}
COMBINED_RECEPTION_COLUMNS = ['reception_autumn_score', 'reception_spring_score', 'reception_summer_score', 'reception_notes']
COMBINED_PHONICS_COLUMNS = ['phonics_y1_score', 'phonics_y2_retake_score', 'phonics_passed']
COMBINED_TIMES_TABLES_COLUMNS = ['times_tables_score', 'times_tables_date']
SATS_COMBINED_FIELDS = ['arithmetic', 'reasoning1', 'reasoning2', 'maths_scaled', 'reading', 'reading_scaled', 'spelling', 'grammar', 'spag_scaled']
COMBINED_SATS_COLUMNS = [f'sats_exam{exam}_{field}' for exam in range(1, 5) for field in SATS_COMBINED_FIELDS]
FOUNDATION_COMBINED_SUBJECTS = ['art', 'computing', 'dt', 'geography', 'history', 'music', 'pe', 're', 'science']
COMBINED_FOUNDATION_COLUMNS = [f'foundation_{term}_{subject}' for term in ('autumn', 'spring', 'summer') for subject in FOUNDATION_COMBINED_SUBJECTS]
COMBINED_TEMPLATE_COLUMNS = (
    COMBINED_PUPIL_COLUMNS
    + [column for terms in COMBINED_SUBJECT_SCORE_COLUMNS.values() for pair in terms.values() for column in pair]
    + [column for pair in COMBINED_WRITING_COLUMNS.values() for column in pair]
    + COMBINED_RECEPTION_COLUMNS
    + COMBINED_PHONICS_COLUMNS
    + COMBINED_TIMES_TABLES_COLUMNS
    + COMBINED_SATS_COLUMNS
    + COMBINED_FOUNDATION_COLUMNS
    + COMBINED_LEGACY_PUPIL_COLUMNS
)
RECEPTION_TEMPLATE_COLUMNS = [
    'pupil_first_name',
    'pupil_last_name',
    'class_name',
    'academic_year',
    'tracking_point',
    'communication_and_language',
    'psed',
    'physical_development',
    'reading',
    'writing',
    'mathematics',
    'understanding_the_world',
    'expressive_arts_and_design',
]
SATS_STANDARD_COLUMN_MAP = {
    'arithmetic': 'maths_arithmetic',
    'reasoning_1': 'maths_reasoning_1',
    'reasoning_2': 'maths_reasoning_2',
    'maths_combined_score': 'maths_raw_total',
    'maths_scaled_score': 'maths_scaled',
    'reading': 'reading_paper',
        'reading_scaled_score': 'reading_scaled',
    'spelling': 'spag_spelling',
    'grammar': 'spag_grammar',
    'spag_combined_score': 'spag_raw_total',
    'spag_scaled_score': 'spag_scaled',
}
SATS_TEMPLATE_COLUMNS = [
    'pupil_first_name',
    'pupil_last_name',
    'class_name',
    'academic_year',
    'exam_number',
    *SATS_STANDARD_COLUMN_MAP.keys(),
]
RECEPTION_AREA_IMPORT_MAP = {
    'communication_and_language': 'communication_language',
    'psed': 'psed',
    'physical_development': 'physical_development',
    'reading': 'reading',
    'writing': 'writing',
    'mathematics': 'mathematics',
    'understanding_the_world': 'understanding_world',
    'expressive_arts_and_design': 'expressive_arts_design',
}


@dataclass
class CsvImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    pupils_created: int = 0
    pupils_updated: int = 0
    subject_results_created: int = 0
    subject_results_updated: int = 0
    writing_results_created: int = 0
    writing_results_updated: int = 0
    manual_results_skipped: int = 0
    validation_errors: int = 0
    rows_processed: int = 0
    rows_skipped: int = 0
    pupils_matched: int = 0
    tracker_entries_created: int = 0
    tracker_entries_updated: int = 0

    def add_error(self, message: str):
        self.errors.append(message)
        self.validation_errors += 1

    def add_message(self, message: str):
        self.errors.append(message)


@dataclass
class RowProgress:
    pupil_created: bool = False
    pupil_updated: bool = False
    subject_created: int = 0
    subject_updated: int = 0
    writing_created: int = 0
    writing_updated: int = 0
    skipped: bool = False
    manual_skips: int = 0


def generate_csv(template_type: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    template_rows = {
        'combined': [
            COMBINED_TEMPLATE_COLUMNS,
            ['Example Pupil', 'Example Class', 'Year 4', '2025/26', 'Male', 'No', 'No', 'No', 'No'] + [''] * (len(COMBINED_TEMPLATE_COLUMNS) - len(COMBINED_PUPIL_COLUMNS)),
        ],
        'reception': [
            RECEPTION_TEMPLATE_COLUMNS,
            ['Ava', 'Brown', 'Reception', '2025/26', 'baseline', 'on_track', 'on_track', 'on_track', 'on_track', 'on_track', 'on_track', 'on_track', 'on_track'],
        ],
        'sats_tracker': [
            SATS_TEMPLATE_COLUMNS,
            ['Ava', 'Brown', 'Year 6', '2025/26', 'Autumn 1', '34', '28', '27', '', '106', '41', '', '109', '30', '29', '', '108'],
        ],
    }
    if template_type not in template_rows:
        raise CsvImportError(f'Unknown template type: {template_type}.')
    for row in template_rows[template_type]:
        writer.writerow(row)
    return output.getvalue()


def parse_uploaded_csv(file_storage) -> list[dict]:
    if not file_storage or not file_storage.filename:
        raise CsvImportError('Choose a CSV file first.')
    text = file_storage.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvImportError('The CSV file is missing a header row.')
    return list(reader)


def _clean_value(value: str | None) -> str:
    return str(value or '').strip()


def _parse_bool(value: str | None) -> bool:
    return _clean_value(value).lower() in {'1', 'true', 'yes', 'y'}


def _parse_optional_int(value: str | None, label: str) -> int | None:
    cleaned = _clean_value(value)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise CsvImportError(f'{label} must be a whole number.') from exc


def _require_value(row: dict, column: str, *, label: str | None = None) -> str:
    value = _clean_value(row.get(column))
    if not value:
        raise CsvImportError(f'{label or column} is required.')
    return value



def _split_pupil_name(row: dict) -> tuple[str, str, str]:
    pupil_name = _clean_value(row.get('pupil'))
    first_name = _clean_value(row.get('first_name'))
    last_name = _clean_value(row.get('last_name'))
    if not pupil_name and (first_name or last_name):
        pupil_name = f'{first_name} {last_name}'.strip()
    if not pupil_name:
        raise CsvImportError('pupil is required.')
    parts = pupil_name.split()
    if not first_name:
        first_name = parts[0]
    if not last_name:
        last_name = ' '.join(parts[1:]) or parts[0]
    return pupil_name, first_name, last_name


def _parse_year_group(value: str | None) -> int:
    raw = _clean_value(value).lower().replace(' ', '')
    aliases = {'reception': 0, 'rec': 0, 'r': 0, 'yearr': 0}
    for year in range(1, 7):
        aliases[str(year)] = year
        aliases[f'y{year}'] = year
        aliases[f'year{year}'] = year
    if raw not in aliases:
        raise CsvImportError('Unknown year group.')
    return aliases[raw]


def _get_or_create_class(class_name: str, year_group: int) -> tuple[SchoolClass, bool]:
    school_id = current_school_id()
    if school_id is None:
        raise CsvImportError('Select a school before importing CSV data.')
    school_class = SchoolClass.query.filter_by(school_id=school_id, name=class_name).first()
    if school_class:
        if school_class.year_group != year_group:
            school_class.year_group = year_group
        school_class.is_active = True
        db.session.add(school_class)
        return school_class, False
    school_class = SchoolClass(name=class_name, year_group=year_group, school_id=school_id, is_active=True, is_demo=getattr(current_user, 'is_demo', False))
    db.session.add(school_class)
    db.session.flush()
    return school_class, True


def _find_combined_pupil(row: dict, first_name: str, last_name: str, pupil_name: str, school_class: SchoolClass) -> Pupil | None:
    school_id = current_school_id()
    pupil_id = _clean_value(row.get('pupil_id'))
    if pupil_id.isdigit():
        found = Pupil.query.filter_by(id=int(pupil_id), school_id=school_id).first()
        if found:
            return found
    found = Pupil.query.filter_by(first_name=first_name, last_name=last_name, class_id=school_class.id, school_id=school_id).first()
    if found:
        return found
    return Pupil.query.filter(Pupil.school_id == school_id, Pupil.class_id == school_class.id, (Pupil.first_name + ' ' + Pupil.last_name) == pupil_name).first()


def _save_class_history(pupil: Pupil, school_class: SchoolClass, academic_year: str) -> None:
    history = PupilClassHistory.query.filter_by(school_id=school_class.school_id, pupil_id=pupil.id, academic_year=academic_year).first()
    if not history:
        history = PupilClassHistory(school_id=school_class.school_id, pupil_id=pupil.id, academic_year=academic_year)
    history.class_name = school_class.name
    history.year_group = school_class.year_group
    history.teacher_username = school_class.teacher.username if school_class.teacher else None
    db.session.add(history)


def _normalize_foundation(value: str | None) -> str | None:
    raw = _clean_value(value).lower()
    if not raw or raw == 'not_assessed':
        return None
    return {'working_towards': 'Working Towards', 'expected': 'On Track', 'working_at': 'On Track', 'exceeding': 'Exceeding'}.get(raw)

def _find_class(class_name: str) -> SchoolClass:
    school_class = school_scoped_query(SchoolClass.query.filter_by(name=class_name.strip()), SchoolClass).first()
    if not school_class:
        raise CsvImportError(f'Class not found: {class_name}.')
    return school_class


def _find_pupil(first_name: str, last_name: str, class_name: str) -> Pupil:
    school_class = _find_class(class_name)
    pupil = school_scoped_query(
        Pupil.query.filter_by(first_name=first_name.strip(), last_name=last_name.strip(), class_id=school_class.id),
        Pupil,
    ).first()
    if not pupil:
        raise CsvImportError(f'Pupil not found: {first_name} {last_name} in {class_name}.')
    return pupil


def _has_any_subject_data(row: dict) -> bool:
    return any(_clean_value(row.get(column)) for columns_by_term in COMBINED_SUBJECT_SCORE_COLUMNS.values() for columns in columns_by_term.values() for column in columns)




def _get_send_value(row: dict) -> str | None:
    for key in ('send', 'SEND', 'sen', 'SEN', 'special_educational_needs', 'special educational needs'):
        if key in row:
            return row.get(key)
    return None

def _has_any_writing_data(row: dict) -> bool:
    return any(_clean_value(row.get(column)) for columns in COMBINED_WRITING_COLUMNS.values() for column in columns)


def _parse_join_year_group(row: dict) -> int | None:
    join_year_group_key = next((key for key in ('join_year_group', 'year_joined', 'joined_year_group') if key in row), None)
    if join_year_group_key is None:
        return None
    raw = _clean_value(row.get(join_year_group_key))
    if raw is None:
        return None
    normalized = raw.lower().replace(' ', '')
    aliases = {'reception': 0, 'rec': 0, 'r': 0}
    for year in range(1, 7):
        aliases[str(year)] = year
        aliases[f'y{year}'] = year
        aliases[f'year{year}'] = year
    if normalized in aliases:
        value = aliases[normalized]
    else:
        raise CsvImportError('join_year_group must be a year from Reception to Year 6.')
    if value < 0 or value > 6:
        raise CsvImportError('join_year_group must be a year from Reception to Year 6.')
    return value


def _parse_join_date(row: dict) -> date | None:
    if 'join_date' not in row:
        return None
    raw = _clean_value(row.get('join_date'))
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise CsvImportError('join_date must be in YYYY-MM-DD format.') from exc


def _update_pupil_fields(pupil: Pupil, row: dict, school_class: SchoolClass) -> bool:
    changed = False
    updates = {
        'gender': normalize_gender(_clean_value(row.get('gender'))) or pupil.gender or '',
        'pupil_premium': _parse_bool(row.get('pupil_premium')),
        'laps': _parse_bool(row.get('laps')),
        'service_child': _parse_bool(row.get('service_child')),
        'send': _parse_bool(_get_send_value(row)),
        'class_id': school_class.id,
        'is_active': True,
    }
    if any(key in row for key in ('join_year_group', 'year_joined', 'joined_year_group')):
        updates['join_year_group'] = _parse_join_year_group(row)
    if 'join_date' in row:
        updates['join_date'] = _parse_join_date(row)
    for field, value in updates.items():
        if getattr(pupil, field) != value:
            setattr(pupil, field, value)
            changed = True
    return changed


def _is_subject_result_incomplete(result: SubjectResult) -> bool:
    return any(value is None for value in (result.paper_1_score, result.paper_2_score, result.combined_score, result.combined_percent, result.band_label))


def _can_write_subject_result(existing: SubjectResult | None) -> tuple[bool, str | None]:
    if existing is None:
        return True, None
    if existing.source == 'csv':
        return True, None
    if existing.source == 'manual':
        return False, 'manual'
    if _is_subject_result_incomplete(existing):
        return True, None
    return False, existing.source or 'protected'


def _write_subject_result(existing: SubjectResult | None, *, pupil: Pupil, academic_year: str, term: str, subject: str, paper_1_score: int | None, paper_2_score: int | None) -> tuple[SubjectResult | None, str | None]:
    if paper_1_score is None and paper_2_score is None:
        return None, None
    allowed, reason = _can_write_subject_result(existing)
    if not allowed:
        return None, reason
    setting = get_subject_setting(pupil.school_class.year_group, subject, term)
    result = existing or SubjectResult(pupil_id=pupil.id, academic_year=academic_year, term=term, subject=subject)
    merged_paper_1 = paper_1_score if paper_1_score is not None else result.paper_1_score
    merged_paper_2 = paper_2_score if paper_2_score is not None else result.paper_2_score
    computed = compute_subject_result_values(setting, merged_paper_1, merged_paper_2)
    result.paper_1_score = merged_paper_1
    result.paper_2_score = merged_paper_2
    result.combined_score = computed['combined_score']
    result.combined_percent = computed['combined_percent']
    result.band_label = computed['band_label']
    result.source = 'csv'
    db.session.add(result)
    return result, None




def _normalize_writing_band(value: str | None) -> str | None:
    raw = _clean_value(value)
    if not raw:
        return None
    text = raw.strip().lower()
    if any(token in text for token in ('working towards','working toward','wts','wt','below')):
        return 'working_towards'
    if text in {'expected', 'working_at'} or any(token in text for token in ('on track','working at','working at are','ot')):
        return 'expected'
    if text in {'exceeding', 'greater_depth'} or any(token in text for token in ('exceeding','greater depth','gds','exs','exc')):
        return 'greater_depth'
    return text
def _is_writing_result_incomplete(result: WritingResult) -> bool:
    return not _clean_value(result.band)


def _can_write_writing_result(existing: WritingResult | None) -> tuple[bool, str | None]:
    if existing is None:
        return True, None
    if getattr(existing, 'source', None) == 'csv':
        return True, None
    if getattr(existing, 'source', None) == 'manual':
        return False, 'manual'
    if _is_writing_result_incomplete(existing):
        return True, None
    return False, 'manual'


def _write_writing_result(existing: WritingResult | None, *, pupil: Pupil, academic_year: str, term: str, band: str, notes: str | None) -> tuple[WritingResult | None, str | None]:
    allowed, reason = _can_write_writing_result(existing)
    if not allowed:
        return None, reason
    if band not in WRITING_BAND_LABELS:
        raise CsvImportError(f'Writing {term} band must be one of {", ".join(WRITING_BAND_LABELS)}.')
    result = existing or WritingResult(pupil_id=pupil.id, academic_year=academic_year, term=term, band=band)
    result.band = band
    result.notes = notes or result.notes or None
    result.source = 'csv'
    db.session.add(result)
    return result, None


def import_combined_results(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    for index, row in enumerate(rows, start=2):
        summary.rows_processed += 1
        try:
            pupil_name, first_name, last_name = _split_pupil_name(row)
            if pupil_name.lower().startswith('example'):
                summary.rows_skipped += 1
                summary.skipped += 1
                continue
            class_name = _require_value(row, 'class_name', label='class_name')
            year_group = _parse_year_group(row.get('year_group'))
            academic_year = _require_value(row, 'academic_year', label='academic_year')
            get_or_create_academic_year(academic_year)

            school_class, class_created = _get_or_create_class(class_name, year_group)
            pupil = _find_combined_pupil(row, first_name, last_name, pupil_name, school_class)
            progress = RowProgress()
            if class_created:
                summary.add_message(f'Row {index}: class to create/imported: {class_name}.')
            if pupil is None:
                pupil = Pupil(
                    first_name=first_name,
                    last_name=last_name,
                    gender=normalize_gender(_clean_value(row.get('gender'))) or '',
                    pupil_premium=_parse_bool(row.get('pupil_premium')),
                    laps=_parse_bool(row.get('laps')),
                    service_child=_parse_bool(row.get('service_child')),
                    send=_parse_bool(_get_send_value(row)),
                    class_id=school_class.id,
                    join_year_group=year_group,
                    join_date=_parse_join_date(row),
                    school_id=school_class.school_id,
                    is_active=True,
                    is_demo=getattr(current_user, 'is_demo', False),
                )
                db.session.add(pupil)
                db.session.flush()
                progress.pupil_created = True
            else:
                progress.pupil_updated = _update_pupil_fields(pupil, row, school_class)
                pupil.first_name = first_name
                pupil.last_name = last_name
                pupil.school_id = school_class.school_id
                db.session.add(pupil)
            _save_class_history(pupil, school_class, academic_year)

            if year_group in {1, 2, 3, 4, 5}:
                for subject, terms in COMBINED_SUBJECT_SCORE_COLUMNS.items():
                    for term, (paper_1_column, paper_2_column) in terms.items():
                        paper_1_score = _parse_optional_int(row.get(paper_1_column), paper_1_column)
                        paper_2_score = _parse_optional_int(row.get(paper_2_column), paper_2_column)
                        if paper_1_score is None and paper_2_score is None:
                            continue
                        existing = SubjectResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, term=term, subject=subject).first()
                        result, reason = _write_subject_result(existing, pupil=pupil, academic_year=academic_year, term=term, subject=subject, paper_1_score=paper_1_score, paper_2_score=paper_2_score)
                        if result is None and reason:
                            progress.manual_skips += 1
                            summary.add_message(f'Row {index}: skipped {subject} {term} for {pupil.full_name} because existing result source is {reason}.')
                        elif result is not None:
                            progress.subject_created += 1 if existing is None else 0
                            progress.subject_updated += 1 if existing is not None else 0
                for term, (band_column, notes_column) in COMBINED_WRITING_COLUMNS.items():
                    raw_band = _clean_value(row.get(band_column))
                    if not raw_band:
                        continue
                    band = _normalize_writing_band(raw_band)
                    notes = _clean_value(row.get(notes_column)) or None
                    existing = WritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, term=term).first()
                    result, reason = _write_writing_result(existing, pupil=pupil, academic_year=academic_year, term=term, band=band, notes=notes)
                    if result is None and reason:
                        progress.manual_skips += 1
                    elif result is not None:
                        progress.writing_created += 1 if existing is None else 0
                        progress.writing_updated += 1 if existing is not None else 0

            if year_group == 0:
                for term in ('autumn', 'spring', 'summer'):
                    score = _clean_value(row.get(f'reception_{term}_score'))
                    if score:
                        entry = ReceptionTrackerEntry.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, tracking_point=term, area_key='overall').first() or ReceptionTrackerEntry(pupil_id=pupil.id, academic_year=academic_year, tracking_point=term, area_key='overall')
                        entry.status = score
                        entry.school_id = school_class.school_id
                        db.session.add(entry)
                        summary.tracker_entries_created += 1
            elif year_group in {1, 2}:
                score_col = 'phonics_y1_score' if year_group == 1 else 'phonics_y2_retake_score'
                score = _parse_optional_int(row.get(score_col), score_col)
                if score is not None:
                    column = PhonicsTestColumn.query.filter_by(school_id=school_class.school_id, year_group=year_group, name=score_col).first() or PhonicsTestColumn(school_id=school_class.school_id, year_group=year_group, name=score_col, display_order=1, is_active=True)
                    db.session.add(column); db.session.flush()
                    rec = PhonicsScore.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, phonics_test_column_id=column.id).first() or PhonicsScore(pupil_id=pupil.id, academic_year=academic_year, phonics_test_column_id=column.id, school_id=school_class.school_id)
                    rec.score = score; db.session.add(rec); summary.tracker_entries_created += 1
            elif year_group == 4:
                score = _parse_optional_int(row.get('times_tables_score'), 'times_tables_score')
                if score is not None:
                    column = TimesTableTestColumn.query.filter_by(year_group=4, name='Combined CSV').first() or TimesTableTestColumn(year_group=4, name='Combined CSV', display_order=1, is_active=True)
                    db.session.add(column); db.session.flush()
                    rec = TimesTableScore.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, times_table_test_column_id=column.id).first() or TimesTableScore(pupil_id=pupil.id, academic_year=academic_year, times_table_test_column_id=column.id, school_id=school_class.school_id)
                    rec.score = score; db.session.add(rec); summary.tracker_entries_created += 1
            elif year_group == 6:
                for exam in range(1, 5):
                    vals = {field: _parse_optional_int(row.get(f'sats_exam{exam}_{field}'), f'sats_exam{exam}_{field}') for field in SATS_COMBINED_FIELDS}
                    if any(value is not None for value in vals.values()):
                        rec = SatsResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, exam_number=exam).first() or SatsResult(pupil_id=pupil.id, academic_year=academic_year, exam_number=exam, subject='combined', assessment_point=exam, school_id=school_class.school_id)
                        rec.arithmetic_score = vals['arithmetic']; rec.reasoning_1_score = vals['reasoning1']; rec.reasoning_2_score = vals['reasoning2']; rec.maths_scaled_score = vals['maths_scaled']
                        rec.reading_score = vals['reading']; rec.reading_scaled_score = vals['reading_scaled']; rec.spelling_score = vals['spelling']; rec.grammar_score = vals['grammar']; rec.spag_scaled_score = vals['spag_scaled']
                        db.session.add(rec); summary.tracker_entries_created += 1

            if year_group in {1, 2, 3, 4, 5}:
                for term in ('autumn', 'spring', 'summer'):
                    for subject in FOUNDATION_COMBINED_SUBJECTS:
                        judgement = _normalize_foundation(row.get(f'foundation_{term}_{subject}'))
                        if judgement is None:
                            continue
                        rec = FoundationResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, half_term=term, subject=subject).first() or FoundationResult(pupil_id=pupil.id, academic_year=academic_year, half_term=term, subject=subject, school_id=school_class.school_id)
                        rec.judgement = judgement
                        rec.updated_by_user_id = getattr(current_user, 'id', None)
                        db.session.add(rec); summary.tracker_entries_created += 1

            summary.pupils_created += 1 if progress.pupil_created else 0
            summary.created += 1 if progress.pupil_created else 0
            summary.pupils_updated += 1 if progress.pupil_updated else 0
            summary.updated += 1 if progress.pupil_updated else 0
            summary.pupils_matched += 0 if progress.pupil_created else 1
            summary.subject_results_created += progress.subject_created
            summary.subject_results_updated += progress.subject_updated
            summary.writing_results_created += progress.writing_created
            summary.writing_results_updated += progress.writing_updated
            summary.manual_results_skipped += progress.manual_skips
            if summary.rows_processed % 100 == 0:
                db.session.flush()
        except Exception as exc:
            summary.rows_skipped += 1
            summary.skipped += 1
            summary.add_error(f'Row {index}: {exc}')
    db.session.flush()
    return summary


def _find_exam_tab_by_name(tab_name: str) -> SatsExamTab:
    clean_name = tab_name.strip().lower()
    if not clean_name:
        raise CsvImportError('exam_tab is required.')
    tab = school_scoped_query(
        SatsExamTab.query.filter(SatsExamTab.year_group == 6, db.func.lower(SatsExamTab.name) == clean_name),
        SatsExamTab,
    ).first()
    if not tab:
        raise CsvImportError(f'Year 6 exam tab not found: {tab_name}.')
    return tab


def import_reception_tracker(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    valid_statuses = {status for status, _ in RECEPTION_STATUS_CHOICES}
    valid_tracking_points = {point for point, _ in RECEPTION_TRACKING_POINTS}
    processed_pupil_ids: set[int] = set()

    for index, row in enumerate(rows, start=2):
        summary.rows_processed += 1
        if summary.rows_processed % 100 == 0:
            db.session.flush()
        try:
            pupil = _find_pupil(row.get('pupil_first_name', ''), row.get('pupil_last_name', ''), row.get('class_name', ''))
            if pupil.school_class.year_group != RECEPTION_YEAR_GROUP:
                raise CsvImportError(f'{pupil.full_name} is not in Reception.')
            processed_pupil_ids.add(pupil.id)
            academic_year = _require_value(row, 'academic_year', label='academic_year')
            get_or_create_academic_year(academic_year)
            tracking_point = _require_value(row, 'tracking_point', label='tracking_point').lower()
            if tracking_point not in valid_tracking_points:
                raise CsvImportError(f'tracking_point must be one of {", ".join(sorted(valid_tracking_points))}.')

            row_updates = 0
            for csv_column, area_key in RECEPTION_AREA_IMPORT_MAP.items():
                status = _clean_value(row.get(csv_column)).lower()
                if not status:
                    continue
                if status not in valid_statuses:
                    raise CsvImportError(f'{csv_column} must be one of {", ".join(sorted(valid_statuses))}.')
                existing = ReceptionTrackerEntry.query.filter_by(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    tracking_point=tracking_point,
                    area_key=area_key,
                ).first()
                if existing is None:
                    existing = ReceptionTrackerEntry(
                        pupil_id=pupil.id,
                        academic_year=academic_year,
                        tracking_point=tracking_point,
                        area_key=area_key,
                    )
                    summary.tracker_entries_created += 1
                    summary.created += 1
                else:
                    summary.tracker_entries_updated += 1
                    summary.updated += 1
                existing.status = status
                db.session.add(existing)
                row_updates += 1
            if row_updates == 0:
                summary.rows_skipped += 1
                summary.skipped += 1
                summary.add_message(f'Row {index}: no Reception area values supplied; row skipped.')
        except Exception as exc:
            summary.rows_skipped += 1
            summary.skipped += 1
            summary.add_error(f'Row {index}: {exc}')
    summary.pupils_matched = len(processed_pupil_ids)
    return summary


def import_sats_tracker_results(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    processed_pupil_ids: set[int] = set()

    for index, row in enumerate(rows, start=2):
        summary.rows_processed += 1
        if summary.rows_processed % 100 == 0:
            db.session.flush()
        try:
            pupil = _find_pupil(row.get('pupil_first_name', ''), row.get('pupil_last_name', ''), row.get('class_name', ''))
            if pupil.school_class.year_group != 6:
                raise CsvImportError(f'{pupil.full_name} is not in Year 6.')
            processed_pupil_ids.add(pupil.id)
            academic_year = _require_value(row, 'academic_year', label='academic_year')
            get_or_create_academic_year(academic_year)
            exam_number = int(_require_value(row, 'exam_number', label='exam_number'))
            per_row_changes = 0
            rec = SatsResult.query.filter_by(
                school_id=pupil.school_id, pupil_id=pupil.id, academic_year=academic_year, exam_number=exam_number
            ).first()
            if rec is None:
                rec = SatsResult(school_id=pupil.school_id, pupil_id=pupil.id, academic_year=academic_year, exam_number=exam_number, subject='maths', assessment_point=exam_number)
                summary.created += 1
            else:
                summary.updated += 1
            for csv_column, field in [('arithmetic', 'arithmetic_score'), ('reasoning_1', 'reasoning_1_score'), ('reasoning_2', 'reasoning_2_score'), ('maths_scaled_score', 'maths_scaled_score'), ('reading', 'reading_score'), ('reading_scaled_score', 'reading_scaled_score'), ('spelling', 'spelling_score'), ('grammar', 'grammar_score'), ('spag_scaled_score', 'spag_scaled_score')]:
                raw_value = _clean_value(row.get(csv_column))
                if raw_value == '':
                    continue
                score = _parse_optional_int(raw_value, csv_column)
                if score is None:
                    continue
                setattr(rec, field, score)
                per_row_changes += 1
            rec.maths_combined_score = (rec.arithmetic_score or 0) + (rec.reasoning_1_score or 0) + (rec.reasoning_2_score or 0)
            rec.spag_combined_score = (rec.spelling_score or 0) + (rec.grammar_score or 0)
            db.session.add(rec)

            if per_row_changes == 0:
                summary.rows_skipped += 1
                summary.skipped += 1
                summary.add_message(f'Row {index}: no SATs values supplied; row skipped.')
        except Exception as exc:
            summary.rows_skipped += 1
            summary.skipped += 1
            summary.add_error(f'Row {index}: {exc}')

    summary.pupils_matched = len(processed_pupil_ids)
    return summary


def export_subject_results_csv(class_id: int | None = None, subject: str | None = None, academic_year: str | None = None, term: str | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'academic_year', 'term', 'subject', 'paper_1_score', 'paper_2_score', 'combined_score', 'combined_percent', 'band_label', 'source', 'notes'])
    query = school_scoped_query(SubjectResult.query.join(SubjectResult.pupil).join(Pupil.school_class), Pupil)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if subject:
        query = query.filter(SubjectResult.subject == subject)
    if academic_year:
        query = query.filter(SubjectResult.academic_year == academic_year)
    if term:
        query = query.filter(SubjectResult.term == term)
    for row in query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.academic_year, row.term, row.subject, row.paper_1_score, row.paper_2_score, row.combined_score, row.combined_percent, short_band_label(row.band_label), row.source, row.notes])
    return output.getvalue()


def export_writing_results_csv(class_id: int | None = None, academic_year: str | None = None, term: str | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'academic_year', 'term', 'band', 'notes', 'source'])
    query = school_scoped_query(WritingResult.query.join(WritingResult.pupil).join(Pupil.school_class), Pupil)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if academic_year:
        query = query.filter(WritingResult.academic_year == academic_year)
    if term:
        query = query.filter(WritingResult.term == term)
    for row in query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.academic_year, row.term, short_band_label(row.band), row.notes, getattr(row, 'source', None)])
    return output.getvalue()


def export_class_overview_csv(academic_year: str, class_id: int | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['class_name', 'year_group', 'teacher', 'pupil_count', 'active_interventions', 'maths_on_track_plus', 'reading_on_track_plus', 'spag_on_track_plus', 'writing_on_track_plus'])
    query = school_scoped_query(SchoolClass.query.filter_by(is_active=True), SchoolClass)
    if class_id:
        query = query.filter(SchoolClass.id == class_id)
    for school_class in query.order_by(SchoolClass.year_group, SchoolClass.name).all():
        row = build_class_overview_row(school_class, academic_year)
        writer.writerow([
            row['class_name'],
            row['year_group'],
            row['teacher_name'],
            row['pupil_count'],
            row['active_interventions'],
            row['subjects']['maths']['on_track_plus'],
            row['subjects']['reading']['on_track_plus'],
            row['subjects']['spag']['on_track_plus'],
            row['subjects']['writing']['on_track_plus'],
        ])
    return output.getvalue()


def export_pupil_overview_csv(academic_year: str | None = None, class_id: int | None = None, send: str = 'all', anonymised: bool = False) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'year_group', 'is_active', 'pupil_premium', 'laps', 'service_child', 'send', 'academic_year', 'gld', 'phonics', 'mtc', 'y6_sats_entries'])
    query = school_scoped_query(Pupil.query.join(Pupil.school_class), Pupil)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if send == 'yes':
        query = query.filter(Pupil.send.is_(True))
    elif send == 'no':
        query = query.filter(or_(Pupil.send.is_(False), Pupil.send.is_(None)))
    selected_year = academic_year or get_selected_current_academic_year()
    for idx, pupil in enumerate(query.order_by(SchoolClass.year_group, SchoolClass.name, Pupil.last_name, Pupil.first_name).all(), start=1):
        overview = build_pupil_overview_data(pupil, selected_year)
        gld = summarize_gld_status(overview['eyfs']['reception_rows']) if pupil.school_class.year_group == 0 else ''
        phonics = max((row.score for row in overview['phonics'] if row.score is not None), default='') if pupil.school_class.year_group in {1, 2} else ''
        mtc = max((row.score for row in overview['mtc'] if row.score is not None), default='') if pupil.school_class.year_group == 4 else ''
        sats_entries = len(overview['sats']) if pupil.school_class.year_group == 6 else ''
        name = f'Pupil {idx}' if anonymised else pupil.full_name
        writer.writerow([name, pupil.school_class.name, pupil.school_class.year_group, pupil.is_active, pupil.pupil_premium, pupil.laps, pupil.service_child, pupil.send, selected_year, gld, phonics, mtc, sats_entries])
    return output.getvalue()


def export_reception_tracker_csv(academic_year: str, tracking_point: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(RECEPTION_TEMPLATE_COLUMNS)
    pupils = (
        school_scoped_query(Pupil.query.join(Pupil.school_class), Pupil)
        .filter(SchoolClass.year_group == RECEPTION_YEAR_GROUP, Pupil.is_active.is_(True))
        .order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name)
        .all()
    )
    entries = (
        ReceptionTrackerEntry.query.filter_by(academic_year=academic_year, tracking_point=tracking_point)
        .filter(ReceptionTrackerEntry.pupil_id.in_([pupil.id for pupil in pupils] or [0]))
        .all()
    )
    lookup = {(entry.pupil_id, entry.area_key): entry.status for entry in entries}
    for pupil in pupils:
        row = [pupil.first_name, pupil.last_name, pupil.school_class.name, academic_year, tracking_point]
        for csv_column, area_key in RECEPTION_AREA_IMPORT_MAP.items():
            row.append(lookup.get((pupil.id, area_key), ''))
        writer.writerow(row)
    return output.getvalue()


def export_sats_tracker_csv(academic_year: str, exam_tab: str) -> str:
    exam_number = int(exam_tab.split(' ')[1]) if exam_tab.lower().startswith('exam ') else 1
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(SATS_TEMPLATE_COLUMNS)
    pupils = (
        school_scoped_query(Pupil.query.join(Pupil.school_class), Pupil)
        .filter(SchoolClass.year_group == 6, Pupil.is_active.is_(True))
        .order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name)
        .all()
    )
    results = SatsResult.query.filter_by(academic_year=academic_year, exam_number=exam_number).filter(SatsResult.pupil_id.in_([pupil.id for pupil in pupils] or [0])).all()
    lookup = {result.pupil_id: result for result in results}
    for pupil in pupils:
        row = [pupil.first_name, pupil.last_name, pupil.school_class.name, academic_year, exam_number]
        rec = lookup.get(pupil.id)
        for field in ['arithmetic_score', 'reasoning_1_score', 'reasoning_2_score', 'maths_combined_score', 'maths_scaled_score', 'reading_score', 'reading_scaled_score', 'spelling_score', 'grammar_score', 'spag_combined_score', 'spag_scaled_score']:
            value = getattr(rec, field) if rec else None
            row.append('' if value is None else value)
        writer.writerow(row)
    return output.getvalue()


def export_sats_results_csv(academic_year: str, class_id: int | None = None, exam_tab_id: int | None = None) -> str:
    output = io.StringIO()
    tabs = get_sats_exam_tabs(6, include_inactive=True)
    selected_tab = next((tab for tab in tabs if tab.id == exam_tab_id), None)
    if not selected_tab:
        selected_tab = next((tab for tab in tabs if tab.is_active), tabs[0] if tabs else None)
    columns = get_sats_columns(6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=True)
    header = ['pupil_name', 'class_name', 'exam_tab'] + [column.name for column in columns]
    writer = csv.writer(output)
    writer.writerow(header)
    query = school_scoped_query(
        Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == 6, Pupil.is_active.is_(True)),
        Pupil,
    )
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    pupils = query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all()
    _, rows, _ = build_sats_tracker_rows(pupils, academic_year, 6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=True)
    for row in rows:
        writer.writerow([row['pupil'].full_name, row['pupil'].school_class.name, selected_tab.name if selected_tab else ''] + [row['results'][column.id].raw_score if row['results'][column.id] else '' for column in columns])
    return output.getvalue()


def export_interventions_csv(academic_year: str, class_id: int | None = None, anonymised: bool = False, current_scores: dict[int, str] | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'subject', 'term', 'current_score', 'is_active', 'auto_flagged', 'reason', 'note'])
    query = school_scoped_query(Intervention.query.join(Intervention.pupil).join(Pupil.school_class), Pupil).filter(Intervention.academic_year == academic_year)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    for idx, row in enumerate(query.order_by(SchoolClass.year_group, SchoolClass.name, Pupil.last_name, Pupil.first_name).all(), start=1):
        name = f'Pupil {idx}' if anonymised else row.pupil.full_name
        writer.writerow([name, row.pupil.school_class.name, row.subject, row.term, (current_scores or {}).get(row.id, '—'), row.is_active, row.auto_flagged, row.reason, row.note])
    return output.getvalue()


def export_history_csv(academic_year: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'academic_year', 'class_name', 'year_group', 'teacher_username', 'promoted_to_year_group'])
    rows = (
        school_scoped_query(PupilClassHistory.query.join(PupilClassHistory.pupil), PupilClassHistory)
        .filter(PupilClassHistory.academic_year == academic_year)
        .order_by(PupilClassHistory.year_group, PupilClassHistory.class_name, Pupil.last_name, Pupil.first_name)
        .all()
    )
    for row in rows:
        writer.writerow([row.pupil.full_name, row.academic_year, row.class_name, row.year_group, row.teacher_username, row.promoted_to_year_group or ''])
    return output.getvalue()
