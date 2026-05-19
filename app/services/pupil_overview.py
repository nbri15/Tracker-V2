"""Central source-of-truth helpers for pupil overview assessment data."""

from __future__ import annotations

from collections import defaultdict

from app.models import (
    FoundationResult,
    PhonicsScore,
    Pupil,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    WritingResult,
)
from .assessments import get_current_academic_year


def get_latest_tracker_data(pupil: Pupil, academic_year: str | None = None) -> dict:
    """Return latest standard tracker + writing rows for a pupil and year."""
    year = academic_year or get_current_academic_year()
    subject_rows = (
        SubjectResult.query.filter_by(pupil_id=pupil.id, academic_year=year)
        .order_by(SubjectResult.updated_at.desc())
        .all()
    )
    writing_rows = (
        WritingResult.query.filter_by(pupil_id=pupil.id, academic_year=year)
        .order_by(WritingResult.updated_at.desc())
        .all()
    )
    return {'subject_rows': subject_rows, 'writing_rows': writing_rows}


def get_y6_sats_data(pupil: Pupil, academic_year: str | None = None) -> list[SatsColumnResult]:
    year = academic_year or get_current_academic_year()
    return (
        SatsColumnResult.query.filter_by(pupil_id=pupil.id, academic_year=year)
        .join(SatsColumnResult.column)
        .order_by(SatsColumnResult.updated_at.desc())
        .all()
    )


def get_sats_data(pupil: Pupil, academic_year: str | None = None) -> list[SatsColumnResult]:
    """Compatibility alias for central SATs data access."""
    return get_y6_sats_data(pupil, academic_year)


def get_phonics_data(pupil: Pupil, academic_year: str | None = None) -> list[PhonicsScore]:
    year = academic_year or get_current_academic_year()
    return PhonicsScore.query.filter_by(pupil_id=pupil.id, academic_year=year).all()


def get_mtc_data(pupil: Pupil, academic_year: str | None = None) -> list[TimesTableScore]:
    year = academic_year or get_current_academic_year()
    return TimesTableScore.query.filter_by(pupil_id=pupil.id, academic_year=year).all()


def get_eyfs_data(pupil: Pupil, academic_year: str | None = None) -> dict:
    year = academic_year or get_current_academic_year()
    reception_rows = (
        ReceptionTrackerEntry.query.filter_by(pupil_id=pupil.id, academic_year=year)
        .order_by(ReceptionTrackerEntry.tracking_point.desc())
        .all()
    )
    foundation_rows = (
        FoundationResult.query.filter_by(pupil_id=pupil.id, academic_year=year)
        .order_by(FoundationResult.half_term.desc(), FoundationResult.subject.asc())
        .all()
    )
    return {'reception_rows': reception_rows, 'foundation_rows': foundation_rows}


def build_pupil_overview_data(pupil: Pupil, academic_year: str | None = None) -> dict:
    """Year-specific overview payload used by pages and exports."""
    year = academic_year or get_current_academic_year()
    year_group = pupil.school_class.year_group if pupil.school_class else None
    payload = {
        'academic_year': year,
        'year_group': year_group,
        'tracker': get_latest_tracker_data(pupil, year),
        'phonics': [],
        'mtc': [],
        'eyfs': {'reception_rows': [], 'foundation_rows': []},
        'sats': [],
    }

    eyfs_data = get_eyfs_data(pupil, year)
    payload['eyfs']['foundation_rows'] = eyfs_data['foundation_rows']
    if year_group == 0:
        payload['eyfs']['reception_rows'] = eyfs_data['reception_rows']
    elif year_group == 1:
        payload['phonics'] = get_phonics_data(pupil, year)
    elif year_group == 2:
        payload['phonics'] = get_phonics_data(pupil, year)
    elif year_group == 4:
        payload['mtc'] = get_mtc_data(pupil, year)
    elif year_group == 6:
        payload['sats'] = get_y6_sats_data(pupil, year)

    return payload


def summarize_gld_status(reception_rows: list[ReceptionTrackerEntry]) -> str:
    """Best-effort GLD status summary from latest reception outcomes."""
    if not reception_rows:
        return '—'
    latest_by_area = {}
    for row in reception_rows:
        latest_by_area.setdefault(row.area_key, row)
    statuses = [r.status for r in latest_by_area.values() if r.status]
    if not statuses:
        return '—'
    secure = sum(1 for value in statuses if value.lower() in {'secure', 'expected', 'exceeding'})
    return 'Likely GLD' if secure >= max(1, round(len(statuses) * 0.75)) else 'Below GLD'
