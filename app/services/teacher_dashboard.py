"""Read-only extras for the teacher dashboard: who needs attention and who has no score yet."""
from __future__ import annotations

from app.models import Intervention, Pupil, SubjectResult
from app.services.assessments import CORE_SUBJECTS, format_subject_name, get_class_pupil_query, get_most_recent_term_with_data
from app.services.intervention_impact import outcomes_for

TERM_LABELS = {'autumn': 'Autumn', 'spring': 'Spring', 'summer': 'Summer'}
WORKING_TOWARDS = 'Working Towards'


def attention_by_subject(school_class, academic_year):
    """For each core subject, using its most recent term with data: pupils below the pass mark
    without active support, and pupils with no score. Nothing is written."""
    pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).order_by(Pupil.last_name, Pupil.first_name).all()
    if not pupils:
        return []
    pupil_ids = [pupil.id for pupil in pupils]
    supported = {}
    for subject, pupil_id in (Intervention.query
            .filter(Intervention.is_active.is_(True), Intervention.academic_year == academic_year, Intervention.pupil_id.in_(pupil_ids))
            .with_entities(Intervention.subject, Intervention.pupil_id).all()):
        supported.setdefault(subject, set()).add(pupil_id)

    cards = []
    for subject in sorted(CORE_SUBJECTS):
        term = get_most_recent_term_with_data(school_class.id, subject, academic_year)
        card = {'subject': subject, 'label': format_subject_name(subject), 'term': term,
                'term_label': TERM_LABELS.get(term, ''), 'needs_support': [], 'missing': [], 'total': len(pupils)}
        if term:
            results = {row.pupil_id: row for row in SubjectResult.query.filter(
                SubjectResult.school_id == school_class.school_id, SubjectResult.pupil_id.in_(pupil_ids),
                SubjectResult.subject == subject, SubjectResult.academic_year == academic_year,
                SubjectResult.term == term).all()}
            for pupil in pupils:
                row = results.get(pupil.id)
                if row is None or row.combined_percent is None:
                    card['missing'].append(pupil)
                elif row.band_label == WORKING_TOWARDS and pupil.id not in supported.get(subject, set()):
                    card['needs_support'].append(pupil)
        cards.append(card)
    return cards


def intervention_progress(active_interventions):
    """Counts of how pupils with active support are doing, from the saved impact outcomes."""
    outcomes = outcomes_for(active_interventions)
    counts = {'improved': 0, 'little_change': 0, 'declined': 0, 'awaiting': 0, 'no_baseline': 0}
    for outcome in outcomes.values():
        status = outcome.get('status')
        if status in counts:
            counts[status] += 1
    counts['total'] = len(active_interventions)
    return counts
