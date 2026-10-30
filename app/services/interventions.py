"""Intervention suggestion and management helpers."""

from __future__ import annotations

from app.extensions import db
from app.models import FoundationResult, Intervention, InterventionProgramme, InterventionProgrammeAssignment, Pupil, SatsColumnResult, SubjectResult, WritingResult


AUTO_REASON = 'Closest pupils below pass threshold'
CORE_SUBJECTS = {'maths', 'reading', 'spag'}


def _band_short_label(label: str | None) -> str | None:
    if not label:
        return None
    mapping = {'Working Towards': 'WT', 'On Track': 'OT', 'Exceeding': 'EXS'}
    return mapping.get(label, label)


def get_current_score_for_intervention(intervention: Intervention) -> str:
    """Return a display-friendly current score string for an intervention row."""
    subject = (intervention.subject or '').strip().lower()
    term = (intervention.term or '').strip().lower()
    academic_year = intervention.academic_year

    if subject in CORE_SUBJECTS:
        row = (
            SubjectResult.query.filter_by(
                pupil_id=intervention.pupil_id,
                academic_year=academic_year,
                subject=subject,
                term=term,
            )
            .order_by(SubjectResult.updated_at.desc(), SubjectResult.id.desc())
            .first()
        )
        if not row:
            return '—'
        if row.combined_percent is not None:
            pct = f'{row.combined_percent:.1f}'.rstrip('0').rstrip('.')
            band = _band_short_label(row.band_label)
            return f'{pct}% · {band}' if band else f'{pct}%'
        if row.combined_score is not None:
            return str(row.combined_score)
        return '—'

    if subject == 'writing':
        row = (
            WritingResult.query.filter_by(
                pupil_id=intervention.pupil_id,
                academic_year=academic_year,
                term=term,
            )
            .order_by(WritingResult.updated_at.desc(), WritingResult.id.desc())
            .first()
        )
        return _band_short_label(row.band) if row else '—'

    if subject in {'sats maths', 'sats reading', 'sats spag', 'year 6 sats'}:
        lookup = {'sats maths': 'maths_scaled', 'sats reading': 'reading_scaled', 'sats spag': 'spag_scaled'}
        key = lookup.get(subject)
        query = SatsColumnResult.query.join(SatsColumnResult.column).filter(
            SatsColumnResult.pupil_id == intervention.pupil_id,
            SatsColumnResult.academic_year == academic_year,
            SatsColumnResult.raw_score.isnot(None),
        )
        if key:
            query = query.filter_by(column_key=key)
        row = query.order_by(SatsColumnResult.updated_at.desc(), SatsColumnResult.id.desc()).first()
        return f'{row.raw_score} scaled' if row else '—'

    row = (
        FoundationResult.query.filter_by(
            pupil_id=intervention.pupil_id,
            academic_year=academic_year,
            subject=subject,
        )
        .order_by(FoundationResult.updated_at.desc(), FoundationResult.id.desc())
        .first()
    )
    return _band_short_label(row.judgement) if row and row.judgement else '—'


def suggest_interventions_for_scope(school_class, subject: str, term: str, academic_year: str, pass_threshold: float) -> list[dict]:
    results = (
        SubjectResult.query.join(SubjectResult.pupil)
        .filter(
            SubjectResult.subject == subject,
            SubjectResult.term == term,
            SubjectResult.academic_year == academic_year,
            Pupil.class_id == school_class.id,
            Pupil.school_id == school_class.school_id,
            SubjectResult.combined_percent.isnot(None),
        )
        .order_by(SubjectResult.combined_percent.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )
    from .assessment_reliability import setting_for_result
    results = [result for result in results if result.combined_percent < setting_for_result(result).below_are_threshold_percent]
    results.sort(key=lambda result: (
        setting_for_result(result).below_are_threshold_percent - result.combined_percent,
        result.pupil.last_name, result.pupil.first_name, result.id))
    suggestions = []
    for result in results[:6]:
        suggestions.append(
            {
                'pupil': result.pupil,
                'subject_result': result,
                'gap_to_pass': round(setting_for_result(result).below_are_threshold_percent - result.combined_percent, 1),
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
            Pupil.school_id == school_class.school_id,
        )
        .all()
    )
    existing_by_pupil = {row.pupil_id: row for row in existing_auto}

    for suggestion in suggestions:
        record = existing_by_pupil.get(suggestion['pupil'].id)
        if record is None:
            teacher_record = Intervention.query.filter_by(
                pupil_id=suggestion['pupil'].id, subject=subject, term=term,
                academic_year=academic_year, school_id=school_class.school_id,
            ).filter((Intervention.is_active.is_(True)) | (Intervention.closed_by_teacher.is_(True))).first()
            if teacher_record:
                continue
            record = Intervention(
                pupil_id=suggestion['pupil'].id,
                subject=subject,
                term=term,
                academic_year=academic_year,
                school_id=school_class.school_id,
                reason=suggestion['reason'],
                auto_flagged=True,
                is_active=True,
                is_demo=school_class.is_demo,
            )
        else:
            record.reason = suggestion['reason']
            if not record.closed_by_teacher:
                record.is_active = True
        db.session.add(record)

    for row in existing_auto:
        if row.pupil_id not in suggested_ids and not row.programme_assignments:
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
            Pupil.school_id == school_class.school_id,
        )
        .order_by(Intervention.auto_flagged.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )


def build_intervention_filters(query, *, year_group: str = '', class_id: str = '', subject: str = '', status: str = 'active', term: str = '', programme_id: str = ''):
    if status not in {'active', 'inactive', 'all'} or (term and term not in {'autumn', 'spring', 'summer'}):
        raise ValueError('Choose a valid status and term.')
    if year_group:
        query = query.filter(Pupil.school_class.has(year_group=int(year_group)))
    if class_id:
        query = query.filter(Pupil.class_id == int(class_id))
    if subject:
        query = query.filter(Intervention.subject == subject)
    if term:
        query = query.filter(Intervention.term == term)
    if programme_id:
        query = query.filter(Intervention.programme_assignments.any(InterventionProgrammeAssignment.programme_id == int(programme_id)))
    if status == 'active':
        query = query.filter(Intervention.is_active.is_(True))
    elif status == 'inactive':
        query = query.filter(Intervention.is_active.is_(False))
    return query


def intervention_assessment(intervention):
    """Exact-term context; a missing result is never shown as zero or another term."""
    from .assessment_reliability import setting_for_result
    row = SubjectResult.query.filter_by(pupil_id=intervention.pupil_id,
        subject=intervention.subject, term=intervention.term,
        academic_year=intervention.academic_year).order_by(SubjectResult.updated_at.desc(), SubjectResult.id.desc()).first()
    context = {'score': get_current_score_for_intervention(intervention), 'threshold': None, 'gap': None}
    if row and row.combined_percent is not None:
        threshold = setting_for_result(row).below_are_threshold_percent
        context.update(threshold=round(threshold, 1), gap=round(max(0, threshold - row.combined_percent), 1))
    return context


def school_programmes(school_id, subject=None, active_only=False):
    query = InterventionProgramme.query.filter_by(school_id=school_id)
    if subject:
        query = query.filter_by(subject=subject)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(InterventionProgramme.subject, InterventionProgramme.name_key)


def assign_programme(school_class, pupil, programme_id, subject, term, academic_year):
    """Idempotent assignment; callers must resolve the pupil through their class scope."""
    programme = school_programmes(school_class.school_id, subject, active_only=True).filter_by(id=programme_id).first()
    if not programme or pupil.school_id != school_class.school_id or pupil.class_id != school_class.id:
        raise ValueError('Choose an available programme and pupil from your class.')
    record = Intervention.query.filter_by(pupil_id=pupil.id, subject=subject, term=term,
        academic_year=academic_year, school_id=school_class.school_id).order_by(Intervention.is_active.desc(), Intervention.id.desc()).first()
    if not record:
        record = Intervention(pupil_id=pupil.id, school_id=school_class.school_id,
            subject=subject, term=term, academic_year=academic_year,
            reason='Teacher assigned support programme', auto_flagged=False, is_demo=school_class.is_demo)
        db.session.add(record)
        db.session.flush()
    record.is_active = True
    record.closed_by_teacher = False
    if not any(item.programme_id == programme.id for item in record.programme_assignments):
        record.programme_assignments.append(InterventionProgrammeAssignment(programme=programme, school_id=school_class.school_id))
    return record
