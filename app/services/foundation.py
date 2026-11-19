"""Service helpers for the Foundation tracker."""

from __future__ import annotations

from collections import Counter

from app.extensions import db
from app.models import FoundationResult, Pupil
from app.services.assessments import get_class_pupil_query, get_latest_previous_assessment

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
JUDGED = ('Working Towards', 'On Track', 'Exceeding')
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
        ghost_judgements = {}
        for subject_key, _subject_label in FOUNDATION_SUBJECTS:
            record = lookup.get((pupil.id, subject_key))
            judgements[subject_key] = record.judgement if record else ''
            notes[subject_key] = record.note if record else ''
            ghost_judgements[subject_key] = '' if record else (
                get_latest_previous_assessment(
                    pupil_id=pupil.id,
                    subject=subject_key,
                    current_term=half_term,
                    academic_year=academic_year,
                ) or ''
            )
        rows.append({'pupil': pupil, 'judgements': judgements, 'ghost_judgements': ghost_judgements, 'notes': notes})
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


def _half_term_label(half_term: str) -> str:
    return dict(FOUNDATION_HALF_TERMS).get(half_term, half_term)


def build_foundation_subject_rows(classes, academic_year: str, subject: str, half_term: str = 'latest') -> dict:
    """Class rows for one Foundation subject, in the same shape the Subject view already uses.

    ``half_term='latest'`` picks the most recent half term that has any judgement saved for this
    subject among these classes' pupils. Returns ``class_rows``, ``top_pupils`` (everyone judged
    Exceeding, grouped by class) and the ``half_term`` actually used.
    """
    pupils_by_class = {}
    for school_class in classes:
        pupils_by_class[school_class.id] = (
            get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).order_by(Pupil.last_name, Pupil.first_name).all()
        )
    all_ids = [pupil.id for pupils in pupils_by_class.values() for pupil in pupils]

    if half_term == 'latest':
        used = set()
        if all_ids:
            used = {
                row[0] for row in db.session.query(FoundationResult.half_term).filter(
                    FoundationResult.pupil_id.in_(all_ids), FoundationResult.academic_year == academic_year,
                    FoundationResult.subject == subject, FoundationResult.judgement.in_(JUDGED),
                ).distinct()
            }
        order = [key for key, _label in FOUNDATION_HALF_TERMS]
        half_term = max(used, key=order.index) if used else order[0]

    judgement_by_pupil = {}
    if all_ids:
        for record in FoundationResult.query.filter(
            FoundationResult.pupil_id.in_(all_ids), FoundationResult.academic_year == academic_year,
            FoundationResult.half_term == half_term, FoundationResult.subject == subject,
        ).all():
            judgement_by_pupil[record.pupil_id] = record.judgement

    class_rows, top_pupils = [], []
    for school_class in classes:
        pupils = pupils_by_class[school_class.id]
        counts = Counter(judgement_by_pupil.get(pupil.id) for pupil in pupils)
        scored = counts['Working Towards'] + counts['On Track'] + counts['Exceeding']
        class_rows.append({
            'class_id': school_class.id, 'class_name': school_class.name, 'year_group': school_class.year_group,
            'teacher_name': school_class.teacher.username if school_class.teacher else 'Unassigned',
            'pupil_count': len(pupils), 'active_interventions': 0,
            'subjects': {subject: {
                'working_towards': counts['Working Towards'], 'on_track': counts['On Track'], 'exceeding': counts['Exceeding'],
                'average_percent': None, 'term_label': _half_term_label(half_term) if scored else 'No data',
            }},
        })
        for pupil in pupils:
            if judgement_by_pupil.get(pupil.id) == 'Exceeding':
                top_pupils.append({'pupil_id': pupil.id, 'name': pupil.full_name, 'class_name': school_class.name, 'year_group': school_class.year_group})
    top_pupils.sort(key=lambda p: (p['year_group'], p['class_name'].lower(), p['name'].lower()))
    return {'class_rows': class_rows, 'top_pupils': top_pupils, 'half_term': half_term, 'half_term_label': _half_term_label(half_term)}
