"""Shared quick-add pupil helpers for teacher and admin flows."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models import Pupil, SchoolClass


def create_quick_add_pupil(*, school_class: SchoolClass, first_name: str, last_name: str, gender: str, pupil_premium: bool, laps: bool, service_child: bool, send: bool, join_year_group_raw: str = '', join_date_raw: str = '') -> tuple[Pupil | None, str | None]:
    first_name = (first_name or '').strip()
    last_name = (last_name or '').strip()
    gender = (gender or '').strip() or 'Unknown'
    if not school_class:
        return None, 'Select a valid class before adding a pupil.'
    if not first_name or not last_name:
        return None, 'Enter both first and last name before adding a pupil.'

    join_year_group = None
    join_year_group_raw = (join_year_group_raw or '').strip()
    if join_year_group_raw != '':
        try:
            join_year_group = int(join_year_group_raw)
        except ValueError:
            return None, 'Year joined school must be a number between Reception and Year 6.'
    if join_year_group is not None and (join_year_group < 0 or join_year_group > 6):
        return None, 'Year joined school must be between Reception and Year 6.'

    parsed_join_date = None
    join_date_raw = (join_date_raw or '').strip()
    if join_date_raw:
        try:
            parsed_join_date = date.fromisoformat(join_date_raw)
        except ValueError:
            return None, 'Join date must be a valid date.'

    duplicate = Pupil.query.filter(
        Pupil.class_id == school_class.id,
        func.lower(Pupil.first_name) == first_name.lower(),
        func.lower(Pupil.last_name) == last_name.lower(),
    ).first()
    if duplicate:
        return None, f'{duplicate.full_name} already exists in {school_class.name}.'

    pupil = Pupil(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        pupil_premium=bool(pupil_premium),
        laps=bool(laps),
        service_child=bool(service_child),
        send=bool(send),
        join_year_group=join_year_group,
        join_date=parsed_join_date,
        class_id=school_class.id,
        school_id=school_class.school_id,
        is_active=True,
        is_demo=school_class.is_demo,
    )
    db.session.add(pupil)
    db.session.commit()
    return pupil, None
