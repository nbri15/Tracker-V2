"""Application setup and self-healing seed helpers."""

from __future__ import annotations

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AcademicYear

DEFAULT_ACADEMIC_YEARS = ('2023/24', '2024/25', '2025/26', '2026/27')
DEFAULT_CURRENT_ACADEMIC_YEAR = '2025/26'


def get_or_create_academic_year(name: str, *, mark_current: bool = False) -> AcademicYear:
    """Return an academic year row, creating it when it is missing."""

    clean_name = (name or '').strip()
    if not clean_name:
        raise ValueError('Academic year name is required.')

    record = AcademicYear.query.filter_by(name=clean_name).first()
    if record is None:
        record = AcademicYear(name=clean_name, is_current=False)
        db.session.add(record)
        db.session.flush()

    if mark_current and not record.is_current:
        AcademicYear.query.update({'is_current': False})
        record.is_current = True
        db.session.add(record)
        db.session.flush()

    return record


def ensure_default_academic_years() -> list[AcademicYear]:
    """Seed the default academic years only when the table is empty."""

    if AcademicYear.query.count() > 0:
        return []

    created: list[AcademicYear] = []
    for year_name in DEFAULT_ACADEMIC_YEARS:
        existing = AcademicYear.query.filter_by(name=year_name).first()
        if existing is not None:
            created.append(existing)
            continue
        record = AcademicYear(
            name=year_name,
            is_current=year_name == DEFAULT_CURRENT_ACADEMIC_YEAR,
            is_archived=False,
        )
        db.session.add(record)
        created.append(record)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return []

    if created:
        current_app.logger.info(
            'Created default academic years:\n%s',
            '\n'.join(year.name for year in created),
        )
    return created


def _parse_academic_year_start(name: str) -> int:
    return int(name.split('/', 1)[0])


def _format_academic_year(start_year: int) -> str:
    return f'{start_year}/{str(start_year + 1)[-2:]}'


def generate_next_missing_academic_years(count: int = 2) -> list[AcademicYear]:
    """Create the next missing academic year rows after the latest known year."""

    existing_names = {year.name for year in AcademicYear.query.all()}
    valid_start_years = []
    for year_name in existing_names:
        try:
            valid_start_years.append(_parse_academic_year_start(year_name))
        except (TypeError, ValueError):
            continue

    next_start_year = (max(valid_start_years) + 1) if valid_start_years else _parse_academic_year_start(DEFAULT_ACADEMIC_YEARS[-1]) + 1
    created: list[AcademicYear] = []
    while len(created) < count:
        year_name = _format_academic_year(next_start_year)
        next_start_year += 1
        if year_name in existing_names:
            continue
        record = AcademicYear(name=year_name, is_current=False, is_archived=False)
        db.session.add(record)
        db.session.flush()
        existing_names.add(year_name)
        created.append(record)

    db.session.commit()
    return created
