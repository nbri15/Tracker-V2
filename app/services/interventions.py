"""Intervention suggestion and management helpers."""

from __future__ import annotations

from app.extensions import db
from app.models import Intervention, Pupil, SubjectResult


AUTO_REASON = 'Closest pupils below pass threshold'


def suggest_interventions_for_scope(school_class, subject: str, term: str, academic_year: str, pass_threshold: float) -> list[dict]:
    results = (
        SubjectResult.query.join(SubjectResult.pupil)
        .filter(
            SubjectResult.subject == subject,
            SubjectResult.term == term,
            SubjectResult.academic_year == academic_year,
            Pupil.class_id == school_class.id,
            SubjectResult.combined_percent.isnot(None),
            SubjectResult.combined_percent < pass_threshold,
        )
        .order_by(SubjectResult.combined_percent.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )
    suggestions = []
    for result in results[:6]:
        suggestions.append(
            {
                'pupil': result.pupil,
                'subject_result': result,
                'gap_to_pass': round(pass_threshold - result.combined_percent, 1),
                'reason': AUTO_REASON,
            }
        )
    return suggestions


def sync_auto_interventions(school_class, subject: str, term: str, academic_year: str, pass_threshold: float) -> list[Intervention]:
    suggestions = suggest_interventions_for_scope(school_class, subject, term, academic_year, pass_threshold)
    suggested_ids = {item['pupil'].id for item in suggestions}
    existing_auto = (
        Intervention.query.join(Intervention.pupil)
        .filter(
            Intervention.subject == subject,
            Intervention.term == term,
            Intervention.academic_year == academic_year,
            Intervention.auto_flagged.is_(True),
            Pupil.class_id == school_class.id,
        )
        .all()
    )
    existing_by_pupil = {row.pupil_id: row for row in existing_auto}

    for suggestion in suggestions:
        record = existing_by_pupil.get(suggestion['pupil'].id)
        if record is None:
            record = Intervention(
                pupil_id=suggestion['pupil'].id,
                subject=subject,
                term=term,
                academic_year=academic_year,
                reason=suggestion['reason'],
                auto_flagged=True,
                is_active=True,
                is_demo=school_class.is_demo,
            )
        else:
            record.reason = suggestion['reason']
            record.is_active = True
        db.session.add(record)

    for row in existing_auto:
        if row.pupil_id not in suggested_ids:
            row.is_active = False
            db.session.add(row)

    db.session.flush()
    return (
        Intervention.query.join(Intervention.pupil)
        .filter(
            Intervention.subject == subject,
            Intervention.term == term,
            Intervention.academic_year == academic_year,
            Intervention.is_active.is_(True),
            Pupil.class_id == school_class.id,
        )
        .order_by(Intervention.auto_flagged.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )


def build_intervention_filters(query, *, year_group: str = '', class_id: str = '', subject: str = '', status: str = 'active'):
    if year_group:
        query = query.filter(Pupil.school_class.has(year_group=int(year_group)))
    if class_id:
        query = query.filter(Pupil.class_id == int(class_id))
    if subject:
        query = query.filter(Intervention.subject == subject)
    if status == 'active':
        query = query.filter(Intervention.is_active.is_(True))
    elif status == 'inactive':
        query = query.filter(Intervention.is_active.is_(False))
    return query
