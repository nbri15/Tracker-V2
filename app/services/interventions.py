"""Intervention suggestion and management helpers."""

from __future__ import annotations

from app.extensions import db
from app.models import FoundationResult, Intervention, Pupil, SatsColumnResult, SubjectResult, WritingResult


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
            row = (
                SubjectResult.query.filter_by(
                    pupil_id=intervention.pupil_id,
                    academic_year=academic_year,
                    subject=subject,
                )
                .order_by(SubjectResult.updated_at.desc(), SubjectResult.id.desc())
                .first()
            )
        if not row:
            return '—'
        if row.combined_percent is not None:
            pct = int(round(row.combined_percent))
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
        if not row:
            row = (
                WritingResult.query.filter_by(pupil_id=intervention.pupil_id, academic_year=academic_year)
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
