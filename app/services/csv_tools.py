"""CSV parsing, validation, import, and export helpers."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from app.extensions import db
from app.models import Intervention, Pupil, PupilClassHistory, SatsColumnResult, SatsColumnSetting, SchoolClass, SubjectResult, WritingResult
from .assessments import CsvImportError, WRITING_BAND_LABELS, build_class_overview_row, compute_subject_result_values, get_subject_setting
from .sats_tracker import build_sats_tracker_rows, get_sats_columns


@dataclass
class CsvImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def generate_csv(template_type: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    template_rows = {
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


def _parse_bool(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y'}


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
        except Exception as exc:  # validation summary pathway
            summary.errors.append(f'Row {index}: {exc}')
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
                summary.errors.append(f'Row {index}: skipped manual result for {pupil.full_name} {subject}.')
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
        except Exception as exc:
            summary.errors.append(f'Row {index}: {exc}')
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
            if existing and existing.notes and 'manual' in (existing.notes or '').lower():
                summary.skipped += 1
                summary.errors.append(f'Row {index}: skipped existing writing row for {pupil.full_name}.')
                continue
            result = existing or WritingResult(pupil_id=pupil.id, academic_year=row['academic_year'].strip(), term=row['term'].strip().lower(), band=band)
            result.band = band
            result.notes = row.get('notes', '').strip() or None
            db.session.add(result)
            summary.created += 0 if existing else 1
            summary.updated += 1 if existing else 0
        except Exception as exc:
            summary.errors.append(f'Row {index}: {exc}')
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
    writer.writerow(['pupil_name', 'class_name', 'academic_year', 'term', 'band', 'notes'])
    query = WritingResult.query.join(WritingResult.pupil).join(Pupil.school_class)
    if class_id:
        query = query.filter(Pupil.class_id == class_id)
    if academic_year:
        query = query.filter(WritingResult.academic_year == academic_year)
    if term:
        query = query.filter(WritingResult.term == term)
    for row in query.order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all():
        writer.writerow([row.pupil.full_name, row.pupil.school_class.name, row.academic_year, row.term, row.band, row.notes])
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
    rows = PupilClassHistory.query.join(PupilClassHistory.pupil).filter(PupilClassHistory.academic_year == academic_year).order_by(PupilClassHistory.year_group, PupilClassHistory.class_name, Pupil.last_name, Pupil.first_name).all()
    for row in rows:
        writer.writerow([row.pupil.full_name, row.academic_year, row.class_name, row.year_group, row.teacher_username, row.promoted_to_year_group or ''])
    return output.getvalue()
