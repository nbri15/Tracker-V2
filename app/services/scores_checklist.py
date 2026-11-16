"""Term-end 'are all the scores in?' check for leaders. Read-only."""
from __future__ import annotations

from app.models import Pupil, SchoolClass, SubjectResult
from app.services.assessments import CORE_SUBJECTS, format_subject_name, get_class_pupil_query


def status_for(total: int, scored: int) -> str:
    """complete / partial / not_started / no_pupils."""
    if total == 0:
        return 'no_pupils'
    if scored >= total:
        return 'complete'
    return 'not_started' if scored == 0 else 'partial'


def build_checklist(school_id, academic_year, term, classes):
    """One entry per class (Year 1 and up): for each core subject how many pupils have a score and who is missing."""
    term = (term or '').strip().lower()
    entries = []
    for school_class in classes:
        if school_class.year_group == 0:
            continue  # Reception uses the EYFS tracker, not termly scores
        pupils = (get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True))
                  .order_by(Pupil.last_name, Pupil.first_name).all())
        pupil_ids = [p.id for p in pupils]
        subjects = []
        for subject in CORE_SUBJECTS:
            scored_ids = {pid for (pid,) in SubjectResult.query.filter(
                SubjectResult.school_id == school_id, SubjectResult.pupil_id.in_(pupil_ids or [0]),
                SubjectResult.subject == subject, SubjectResult.academic_year == academic_year,
                SubjectResult.term == term, SubjectResult.combined_percent.isnot(None)).with_entities(SubjectResult.pupil_id).all()}
            missing = [p for p in pupils if p.id not in scored_ids]
            subjects.append({'subject': subject, 'label': format_subject_name(subject), 'total': len(pupils),
                             'scored': len(pupils) - len(missing), 'missing': missing,
                             'status': status_for(len(pupils), len(pupils) - len(missing))})
        entries.append({'class': school_class, 'subjects': subjects})
    return entries


def headline(entries):
    cells = [s for e in entries for s in e['subjects'] if s['status'] != 'no_pupils']
    return {'complete': sum(1 for c in cells if c['status'] == 'complete'), 'total': len(cells)}
