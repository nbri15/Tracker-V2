"""Service helpers for the Foundation tracker."""

from __future__ import annotations

from collections import Counter

from app.extensions import db
from app.models import FoundationResult, Pupil

FOUNDATION_SUBJECTS = (
    ('re', 'RE'),
    ('science', 'Science'),
    ('history', 'History'),
    ('geography', 'Geography'),
    ('dt', 'DT'),
    ('art', 'Art'),
    ('pe', 'PE'),
)
FOUNDATION_HALF_TERMS = (
    ('autumn_1', 'Autumn 1'),
    ('autumn_2', 'Autumn 2'),
    ('spring_1', 'Spring 1'),
    ('spring_2', 'Spring 2'),
    ('summer_1', 'Summer 1'),
    ('summer_2', 'Summer 2'),
)
FOUNDATION_JUDGEMENTS = (
    ('', 'Not assessed'),
    ('Working Towards', 'Working Towards'),
    ('On Track', 'On Track'),
    ('Exceeding', 'Exceeding'),
)
FOUNDATION_JUDGEMENT_THEMES = {
    'Working Towards': 'band-wts',
    'On Track': 'band-ot',
    'Exceeding': 'band-gds',
}


class FoundationValidationError(ValueError):
    """Raised when foundation tracker input is invalid."""


def get_foundation_half_term(value: str | None) -> str:
    half_term = (value or FOUNDATION_HALF_TERMS[0][0]).strip().lower()
    valid_values = {item[0] for item in FOUNDATION_HALF_TERMS}
    return half_term if half_term in valid_values else FOUNDATION_HALF_TERMS[0][0]


def build_foundation_tracker_rows(pupils: list[Pupil], academic_year: str, half_term: str) -> list[dict]:
    pupil_ids = [pupil.id for pupil in pupils]
    rows = []
    results = []
    if pupil_ids:
        results = (
            FoundationResult.query.filter(
                FoundationResult.pupil_id.in_(pupil_ids),
                FoundationResult.academic_year == academic_year,
                FoundationResult.half_term == half_term,
            )
            .order_by(FoundationResult.subject)
            .all()
        )

    lookup = {(record.pupil_id, record.subject): record for record in results}
    for pupil in pupils:
        judgements = {}
        notes = {}
        for subject_key, _subject_label in FOUNDATION_SUBJECTS:
            record = lookup.get((pupil.id, subject_key))
            judgements[subject_key] = record.judgement if record else ''
            notes[subject_key] = record.note if record else ''
        rows.append({'pupil': pupil, 'judgements': judgements, 'notes': notes})
    return rows


def build_foundation_summary(rows: list[dict]) -> dict:
    judgement_counter = Counter({'Working Towards': 0, 'On Track': 0, 'Exceeding': 0, 'Missing': 0})
    subject_summary = {
        subject_key: Counter({'Working Towards': 0, 'On Track': 0, 'Exceeding': 0, 'Missing': 0})
        for subject_key, _label in FOUNDATION_SUBJECTS
    }

    for row in rows:
        for subject_key, _subject_label in FOUNDATION_SUBJECTS:
            judgement = row['judgements'].get(subject_key)
            key = judgement if judgement in {'Working Towards', 'On Track', 'Exceeding'} else 'Missing'
            judgement_counter[key] += 1
            subject_summary[subject_key][key] += 1

    return {'overall': judgement_counter, 'by_subject': subject_summary}


def save_foundation_results(pupils: list[Pupil], academic_year: str, half_term: str, form_data, user_id: int | None = None) -> None:
    pupil_ids = [pupil.id for pupil in pupils]
    if not pupil_ids:
        return

    subject_keys = [subject_key for subject_key, _label in FOUNDATION_SUBJECTS]
    existing_rows = (
        FoundationResult.query.filter(
            FoundationResult.pupil_id.in_(pupil_ids),
            FoundationResult.academic_year == academic_year,
            FoundationResult.half_term == half_term,
            FoundationResult.subject.in_(subject_keys),
        ).all()
    )
    existing_lookup = {(row.pupil_id, row.subject): row for row in existing_rows}

    valid_judgements = {value for value, _label in FOUNDATION_JUDGEMENTS}
    for pupil in pupils:
        for subject_key, _subject_label in FOUNDATION_SUBJECTS:
            judgement = (form_data.get(f'judgement_{pupil.id}_{subject_key}', '') or '').strip()
            note = (form_data.get(f'note_{pupil.id}_{subject_key}', '') or '').strip()
            if judgement not in valid_judgements:
                raise FoundationValidationError('Invalid judgement selected.')

            record = existing_lookup.get((pupil.id, subject_key))
            if judgement == '' and note == '':
                if record:
                    db.session.delete(record)
                continue

            if not record:
                record = FoundationResult(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    half_term=half_term,
                    subject=subject_key,
                )

            record.judgement = judgement or None
            record.note = note or None
            record.updated_by_user_id = user_id
            db.session.add(record)
