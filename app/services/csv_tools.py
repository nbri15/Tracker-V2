"""CSV parsing, validation, import, and export helpers."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.extensions import db
from app.models import Intervention, Pupil, PupilClassHistory, SatsColumnResult, SatsColumnSetting, SchoolClass, SubjectResult, WritingResult
from .assessments import CsvImportError, WRITING_BAND_LABELS, build_class_overview_row, compute_subject_result_values, get_subject_setting
from .sats_tracker import build_sats_tracker_rows, get_sats_columns

COMBINED_PUPIL_COLUMNS = [
    'first_name',
    'last_name',
    'gender',
    'pupil_premium',
    'laps',
    'service_child',
    'class_name',
    'academic_year',
]
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
COMBINED_TEMPLATE_COLUMNS = COMBINED_PUPIL_COLUMNS + [
    'maths_autumn_paper1',
    'maths_autumn_paper2',
    'maths_spring_paper1',
    'maths_spring_paper2',
    'maths_summer_paper1',
    'maths_summer_paper2',
    'reading_autumn_paper1',
    'reading_autumn_paper2',
    'reading_spring_paper1',
    'reading_spring_paper2',
    'reading_summer_paper1',
    'reading_summer_paper2',
    'spag_autumn_paper1',
    'spag_autumn_paper2',
    'spag_spring_paper1',
    'spag_spring_paper2',
    'spag_summer_paper1',
    'spag_summer_paper2',
    'writing_autumn_band',
    'writing_autumn_notes',
    'writing_spring_band',
    'writing_spring_notes',
    'writing_summer_band',
    'writing_summer_notes',
]


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
            [
                'Ava', 'Brown', 'Female', 'false', 'false', 'false', 'Year 1', '2025/26',
                '18', '17', '', '', '', '',
                '22', '18', '', '', '', '',
                '', '', '', '', '', '',
                'expected', 'Autumn moderation complete', '', '', '', '',
            ],
        ],
        'pupils': [
            ['first_name', 'last_name', 'gender', 'pupil_premium', 'laps', 'service_child', 'class_name'],
            ['Ava', 'Brown', 'Female', 'false', 'false', 'false', 'Year 1'],
        ],
        'subject_results': [
            ['pupil_first_name', 'pupil_last_name', 'class_name', 'academic_year', 'term', 'subject', 'paper_1_score', 'paper_2_score', 'combined_score', 'notes'],
            ['Ava', 'Brown', 'Year 1', '2025/26', 'autumn', 'maths', '18', '17', '', 'Imported baseline'],
        ],
        'writing_results': [
            ['pupil_first_name', 'pupil_last_name', 'class_name', 'academic_year', 'term', 'band', 'notes'],
            ['Ava', 'Brown', 'Year 1', '2025/26', 'autumn', 'expected', 'Teacher moderation'],
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


def _find_class(class_name: str) -> SchoolClass:
    school_class = SchoolClass.query.filter_by(name=class_name.strip()).first()
    if not school_class:
        raise CsvImportError(f'Class not found: {class_name}.')
    return school_class


def _find_pupil(first_name: str, last_name: str, class_name: str) -> Pupil:
    school_class = _find_class(class_name)
    pupil = Pupil.query.filter_by(first_name=first_name.strip(), last_name=last_name.strip(), class_id=school_class.id).first()
    if not pupil:
        raise CsvImportError(f'Pupil not found: {first_name} {last_name} in {class_name}.')
    return pupil


def _has_any_subject_data(row: dict) -> bool:
    return any(_clean_value(row.get(column)) for columns_by_term in COMBINED_SUBJECT_SCORE_COLUMNS.values() for columns in columns_by_term.values() for column in columns)


def _has_any_writing_data(row: dict) -> bool:
    return any(_clean_value(row.get(column)) for columns in COMBINED_WRITING_COLUMNS.values() for column in columns)


def _update_pupil_fields(pupil: Pupil, row: dict, school_class: SchoolClass) -> bool:
    changed = False
    updates = {
        'gender': _clean_value(row.get('gender')) or pupil.gender or 'Unknown',
        'pupil_premium': _parse_bool(row.get('pupil_premium')),
        'laps': _parse_bool(row.get('laps')),
        'service_child': _parse_bool(row.get('service_child')),
        'class_id': school_class.id,
        'is_active': True,
    }
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


def import_pupils(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    for index, row in enumerate(rows, start=2):
        try:
            school_class = _find_class(row['class_name'])
            pupil = Pupil.query.filter_by(first_name=row['first_name'].strip(), last_name=row['last_name'].strip(), class_id=school_class.id).first()
            if pupil:
                pupil.gender = row['gender'].strip() or pupil.gender
                pupil.pupil_premium = _parse_bool(row.get('pupil_premium'))
                pupil.laps = _parse_bool(row.get('laps'))
                pupil.service_child = _parse_bool(row.get('service_child'))
                summary.updated += 1
                summary.pupils_updated += 1
            else:
                pupil = Pupil(
                    first_name=row['first_name'].strip(),
                    last_name=row['last_name'].strip(),
                    gender=row['gender'].strip() or 'Unknown',
                    pupil_premium=_parse_bool(row.get('pupil_premium')),
                    laps=_parse_bool(row.get('laps')),
                    service_child=_parse_bool(row.get('service_child')),
                    class_id=school_class.id,
                )
                db.session.add(pupil)
                summary.created += 1
                summary.pupils_created += 1
        except Exception as exc:  # validation summary pathway
            summary.add_error(f'Row {index}: {exc}')
    return summary


def import_subject_results(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    for index, row in enumerate(rows, start=2):
        try:
            pupil = _find_pupil(row['pupil_first_name'], row['pupil_last_name'], row['class_name'])
            subject = row['subject'].strip().lower()
            setting = get_subject_setting(pupil.school_class.year_group, subject, row['term'].strip().lower())
            existing = SubjectResult.query.filter_by(
                pupil_id=pupil.id,
                academic_year=row['academic_year'].strip(),
                term=row['term'].strip().lower(),
                subject=subject,
            ).first()
            if existing and existing.source == 'manual':
                summary.skipped += 1
                summary.manual_results_skipped += 1
                summary.add_message(f'Row {index}: skipped manual result for {pupil.full_name} {subject}.')
                continue
            paper_1_score = int(row['paper_1_score']) if str(row.get('paper_1_score', '')).strip() else None
            paper_2_score = int(row['paper_2_score']) if str(row.get('paper_2_score', '')).strip() else None
            result = existing or SubjectResult(
                pupil_id=pupil.id,
                academic_year=row['academic_year'].strip(),
                term=row['term'].strip().lower(),
                subject=subject,
            )
            result.paper_1_score = paper_1_score
            result.paper_2_score = paper_2_score
            computed = compute_subject_result_values(setting, paper_1_score, paper_2_score)
            result.combined_score = int(row['combined_score']) if str(row.get('combined_score', '')).strip() else computed['combined_score']
            result.combined_percent = SubjectResult.calculate_percent(result.combined_score, setting.combined_max)
            result.band_label = SubjectResult.calculate_band_label(result.combined_percent, setting.below_are_threshold_percent, setting.exceeding_threshold_percent)
            result.source = 'csv'
            result.notes = row.get('notes', '').strip() or None
            db.session.add(result)
            summary.created += 0 if existing else 1
            summary.updated += 1 if existing else 0
            summary.subject_results_created += 0 if existing else 1
            summary.subject_results_updated += 1 if existing else 0
        except Exception as exc:
            summary.add_error(f'Row {index}: {exc}')
    return summary


def import_writing_results(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    for index, row in enumerate(rows, start=2):
        try:
            pupil = _find_pupil(row['pupil_first_name'], row['pupil_last_name'], row['class_name'])
            band = row['band'].strip().lower()
            if band not in WRITING_BAND_LABELS:
                raise CsvImportError(f'band must be one of {", ".join(WRITING_BAND_LABELS)}.')
            existing = WritingResult.query.filter_by(pupil_id=pupil.id, academic_year=row['academic_year'].strip(), term=row['term'].strip().lower()).first()
            existing_source = getattr(existing, 'source', None) if existing else None
            if existing and existing_source == 'manual':
                summary.skipped += 1
                summary.manual_results_skipped += 1
                summary.add_message(f'Row {index}: skipped existing writing row for {pupil.full_name}.')
                continue
            result = existing or WritingResult(pupil_id=pupil.id, academic_year=row['academic_year'].strip(), term=row['term'].strip().lower(), band=band)
            result.band = band
            result.notes = row.get('notes', '').strip() or None
            result.source = 'csv'
            db.session.add(result)
            summary.created += 0 if existing else 1
            summary.updated += 1 if existing else 0
            summary.writing_results_created += 0 if existing else 1
            summary.writing_results_updated += 1 if existing else 0
        except Exception as exc:
            summary.add_error(f'Row {index}: {exc}')
    return summary


def import_combined_results(rows: list[dict]) -> CsvImportSummary:
    summary = CsvImportSummary()
    for index, row in enumerate(rows, start=2):
        summary.rows_processed += 1
        try:
            with db.session.begin_nested():
                school_class = _find_class(_require_value(row, 'class_name', label='class_name'))
                first_name = _require_value(row, 'first_name', label='first_name')
                last_name = _require_value(row, 'last_name', label='last_name')
                academic_year = _require_value(row, 'academic_year', label='academic_year')

                pupil = Pupil.query.filter_by(first_name=first_name, last_name=last_name, class_id=school_class.id).first()
                progress = RowProgress()
                if pupil is None:
                    pupil = Pupil(
                        first_name=first_name,
                        last_name=last_name,
                        gender=_clean_value(row.get('gender')) or 'Unknown',
                        pupil_premium=_parse_bool(row.get('pupil_premium')),
                        laps=_parse_bool(row.get('laps')),
                        service_child=_parse_bool(row.get('service_child')),
                        class_id=school_class.id,
                        is_active=True,
                    )
                    db.session.add(pupil)
                    db.session.flush()
                    progress.pupil_created = True
                else:
                    progress.pupil_updated = _update_pupil_fields(pupil, row, school_class)
                    db.session.add(pupil)

                if not _has_any_subject_data(row) and not _has_any_writing_data(row):
                    progress.skipped = True

                for subject, terms in COMBINED_SUBJECT_SCORE_COLUMNS.items():
                    for term, (paper_1_column, paper_2_column) in terms.items():
                        paper_1_score = _parse_optional_int(row.get(paper_1_column), paper_1_column)
                        paper_2_score = _parse_optional_int(row.get(paper_2_column), paper_2_column)
                        if paper_1_score is None and paper_2_score is None:
                            continue
                        existing = SubjectResult.query.filter_by(
                            pupil_id=pupil.id,
                            academic_year=academic_year,
                            term=term,
                            subject=subject,
                        ).first()
                        result, reason = _write_subject_result(
                            existing,
                            pupil=pupil,
                            academic_year=academic_year,
                            term=term,
                            subject=subject,
                            paper_1_score=paper_1_score,
                            paper_2_score=paper_2_score,
                        )
                        if result is None and reason:
                            progress.manual_skips += 1
                            summary.add_message(
                                f'Row {index}: skipped {subject} {term} for {pupil.full_name} because the existing result source is {reason}.'
                            )
                            continue
                        if result is not None:
                            if existing is None:
                                progress.subject_created += 1
                            else:
                                progress.subject_updated += 1

                for term, (band_column, notes_column) in COMBINED_WRITING_COLUMNS.items():
                    band = _clean_value(row.get(band_column)).lower()
                    notes = _clean_value(row.get(notes_column)) or None
                    if not band:
                        continue
                    existing = WritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, term=term).first()
                    result, reason = _write_writing_result(
                        existing,
                        pupil=pupil,
                        academic_year=academic_year,
                        term=term,
                        band=band,
                        notes=notes,
                    )
                    if result is None and reason:
                        progress.manual_skips += 1
                        summary.add_message(
                            f'Row {index}: skipped writing {term} for {pupil.full_name} because the existing result source is {reason}.'
                        )
                        continue
                    if result is not None:
                        if existing is None:
                            progress.writing_created += 1
                        else:
                            progress.writing_updated += 1

                summary.pupils_created += 1 if progress.pupil_created else 0
                summary.created += 1 if progress.pupil_created else 0
                summary.pupils_updated += 1 if progress.pupil_updated else 0
                summary.updated += 1 if progress.pupil_updated else 0
                summary.subject_results_created += progress.subject_created
                summary.subject_results_updated += progress.subject_updated
                summary.writing_results_created += progress.writing_created
                summary.writing_results_updated += progress.writing_updated
                summary.manual_results_skipped += progress.manual_skips
                if progress.skipped and not any((progress.pupil_created, progress.pupil_updated, progress.subject_created, progress.subject_updated, progress.writing_created, progress.writing_updated)):
                    summary.rows_skipped += 1
                    summary.skipped += 1
        except Exception as exc:
            summary.rows_skipped += 1
            summary.skipped += 1
            summary.add_error(f'Row {index}: {exc}')
    return summary


def export_subject_results_csv(class_id: int | None = None, subject: str | None = None, academic_year: str | None = None, term: str | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'academic_year', 'term', 'subject', 'paper_1_score', 'paper_2_score', 'combined_score', 'combined_percent', 'band_label', 'source', 'notes'])
    query = SubjectResult.query.join(SubjectResult.pupil).join(Pupil.school_class)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if subject:
        query = query.filter(SubjectResult.subject == subject)
    if academic_year:
        query = query.filter(SubjectResult.academic_year == academic_year)
    if term:
        query = query.filter(SubjectResult.term == term)
    for row in query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.academic_year, row.term, row.subject, row.paper_1_score, row.paper_2_score, row.combined_score, row.combined_percent, row.band_label, row.source, row.notes])
    return output.getvalue()


def export_writing_results_csv(class_id: int | None = None, academic_year: str | None = None, term: str | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'academic_year', 'term', 'band', 'notes', 'source'])
    query = WritingResult.query.join(WritingResult.pupil).join(Pupil.school_class)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if academic_year:
        query = query.filter(WritingResult.academic_year == academic_year)
    if term:
        query = query.filter(WritingResult.term == term)
    for row in query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.academic_year, row.term, row.band, row.notes, getattr(row, 'source', None)])
    return output.getvalue()


def export_class_overview_csv(academic_year: str, class_id: int | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['class_name', 'year_group', 'teacher', 'pupil_count', 'active_interventions', 'maths_on_track_plus', 'reading_on_track_plus', 'spag_on_track_plus', 'writing_on_track_plus'])
    query = SchoolClass.query.filter_by(is_active=True)
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


def export_pupil_overview_csv(academic_year: str | None = None, class_id: int | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'year_group', 'is_active', 'pupil_premium', 'laps', 'service_child', 'academic_year'])
    query = Pupil.query.join(Pupil.school_class)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    for pupil in query.order_by(SchoolClass.year_group, SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([pupil.full_name, pupil.school_class.name, pupil.school_class.year_group, pupil.is_active, pupil.pupil_premium, pupil.laps, pupil.service_child, academic_year or 'current'])
    return output.getvalue()


def export_sats_results_csv(academic_year: str, class_id: int | None = None) -> str:
    output = io.StringIO()
    columns = get_sats_columns(6, active_only=True)
    header = ['pupil_name', 'class_name'] + [column.name for column in columns]
    writer = csv.writer(output)
    writer.writerow(header)
    query = Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == 6, Pupil.is_active.is_(True))
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    pupils = query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all()
    _, rows, _ = build_sats_tracker_rows(pupils, academic_year, 6, active_only=True)
    for row in rows:
        writer.writerow([row['pupil'].full_name, row['pupil'].school_class.name] + [row['results'][column.id].raw_score if row['results'][column.id] else '' for column in columns])
    return output.getvalue()


def export_interventions_csv(academic_year: str, class_id: int | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'class_name', 'subject', 'term', 'is_active', 'auto_flagged', 'reason', 'note'])
    query = Intervention.query.join(Intervention.pupil).join(Pupil.school_class).filter(Intervention.academic_year == academic_year)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    for row in query.order_by(SchoolClass.year_group, SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.subject, row.term, row.is_active, row.auto_flagged, row.reason, row.note])
    return output.getvalue()


def export_history_csv(academic_year: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['pupil_name', 'academic_year', 'class_name', 'year_group', 'teacher_username', 'promoted_to_year_group'])
    rows = (
        PupilClassHistory.query.join(PupilClassHistory.pupil)
        .filter(PupilClassHistory.academic_year == academic_year)
        .order_by(PupilClassHistory.year_group, PupilClassHistory.class_name, Pupil.last_name, Pupil.first_name)
        .all()
    )
    for row in rows:
        writer.writerow([row.pupil.full_name, row.academic_year, row.class_name, row.year_group, row.teacher_username, row.promoted_to_year_group or ''])
    return output.getvalue()
