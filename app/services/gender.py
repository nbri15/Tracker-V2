"""Gender normalization helpers."""

from __future__ import annotations

from sqlalchemy import func

from app.models import Pupil

CANONICAL_GENDERS = ('Male', 'Female')


def normalize_gender(value: str | None) -> str | None:
    raw = (value or '').strip()
    if not raw:
        return None
    key = raw.lower()
    if key in {'m', 'male'}:
        return 'Male'
    if key in {'f', 'female'}:
        return 'Female'
    return None


def gender_filter_clause(value: str):
    normalized = normalize_gender(value)
    if normalized == 'Male':
        return func.lower(func.trim(Pupil.gender)).in_(['male', 'm'])
    if normalized == 'Female':
        return func.lower(func.trim(Pupil.gender)).in_(['female', 'f'])
    return None
