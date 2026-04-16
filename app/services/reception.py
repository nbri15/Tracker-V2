"""Reception EYFS tracker helpers."""

from __future__ import annotations

from app.extensions import db
from app.models import ReceptionTrackerEntry, SchoolClass

RECEPTION_YEAR_GROUP = 0
RECEPTION_CLASS_NAME = 'Reception'

RECEPTION_TRACKING_POINTS = [
    ('baseline', 'Baseline'),
    ('autumn_2', 'Autumn 2'),
    ('spring_1', 'Spring 1'),
    ('spring_2', 'Spring 2'),
    ('summer_1', 'Summer 1'),
    ('elg', 'ELG'),
]

RECEPTION_AREAS = [
    ('communication_language', 'Communication and Language'),
    ('psed', 'Personal, Social and Emotional Development'),
    ('physical_development', 'Physical Development'),
    ('reading', 'Reading'),
    ('writing', 'Writing'),
    ('mathematics', 'Mathematics'),
    ('understanding_world', 'Understanding the World'),
    ('expressive_arts_design', 'Expressive Arts and Design'),
]

RECEPTION_STATUS_CHOICES = [
    ('not_on_track', 'Not on track'),
    ('on_track', 'On Track'),
]


class ReceptionTrackerValidationError(ValueError):
    """Raised when reception tracker inputs are invalid."""


def get_reception_class() -> SchoolClass | None:
    """Return the active reception class record if it exists."""

    return SchoolClass.query.filter_by(is_active=True, year_group=RECEPTION_YEAR_GROUP).order_by(SchoolClass.name).first()


def ensure_reception_class() -> SchoolClass:
    """Create/refresh the reception class row if needed."""

    school_class = SchoolClass.query.filter_by(name=RECEPTION_CLASS_NAME).first()
    if not school_class:
        school_class = SchoolClass(name=RECEPTION_CLASS_NAME, year_group=RECEPTION_YEAR_GROUP, is_active=True)
    school_class.name = RECEPTION_CLASS_NAME
    school_class.year_group = RECEPTION_YEAR_GROUP
    school_class.is_active = True
    db.session.add(school_class)
    db.session.flush()
    return school_class


def can_access_reception_tracker(user, school_class: SchoolClass | None = None) -> bool:
    """Return whether the user can access reception tracker pages."""

    if not user or not user.is_authenticated:
        return False
    if user.is_admin:
        return True
    if not user.is_teacher:
        return False
    if school_class is None:
        school_class = get_reception_class()
    return bool(school_class and school_class.teacher_id == user.id)


def get_tracking_point_key(raw_key: str | None) -> str:
    """Validate and normalize the selected tracking point key."""

    default_key = RECEPTION_TRACKING_POINTS[0][0]
    key = (raw_key or default_key).strip().lower()
    valid_keys = {item[0] for item in RECEPTION_TRACKING_POINTS}
    if key not in valid_keys:
        return default_key
    return key


def save_reception_tracker_entries(pupils: list, academic_year: str, tracking_point: str, form_data) -> None:
    """Persist all reception statuses for one tracking point in bulk."""

    valid_statuses = {choice[0] for choice in RECEPTION_STATUS_CHOICES}
    area_keys = [area_key for area_key, _ in RECEPTION_AREAS]

    for pupil in pupils:
        for area_key in area_keys:
            field_key = f'status_{pupil.id}_{area_key}'
            status = (form_data.get(field_key, 'not_on_track') or 'not_on_track').strip().lower()
            if status not in valid_statuses:
                raise ReceptionTrackerValidationError(f'Invalid status for {pupil.full_name} ({area_key}).')
            entry = ReceptionTrackerEntry.query.filter_by(
                pupil_id=pupil.id,
                academic_year=academic_year,
                tracking_point=tracking_point,
                area_key=area_key,
            ).first()
            if not entry:
                entry = ReceptionTrackerEntry(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    tracking_point=tracking_point,
                    area_key=area_key,
                )
            entry.status = status
            db.session.add(entry)


def build_reception_tracker_rows(pupils: list, academic_year: str, tracking_point: str) -> list[dict]:
    """Build spreadsheet rows for the reception tracker page."""

    entries = (
        ReceptionTrackerEntry.query.filter(
            ReceptionTrackerEntry.pupil_id.in_([pupil.id for pupil in pupils] or [-1]),
            ReceptionTrackerEntry.academic_year == academic_year,
            ReceptionTrackerEntry.tracking_point == tracking_point,
        )
        .all()
    )
    status_by_scope = {(entry.pupil_id, entry.area_key): entry.status for entry in entries}

    rows = []
    for pupil in pupils:
        statuses = {
            area_key: status_by_scope.get((pupil.id, area_key), 'not_on_track')
            for area_key, _ in RECEPTION_AREAS
        }
        rows.append({'pupil': pupil, 'statuses': statuses})
    return rows


def build_reception_summary(rows: list[dict]) -> dict[str, dict[str, float | int]]:
    """Compute per-area on-track totals and percentages for headline summary."""

    total_pupils = len(rows)
    summary: dict[str, dict[str, float | int]] = {}
    for area_key, _ in RECEPTION_AREAS:
        on_track = sum(1 for row in rows if row['statuses'].get(area_key) == 'on_track')
        not_on_track = total_pupils - on_track
        percent_on_track = round((on_track / total_pupils) * 100, 1) if total_pupils else 0.0
        summary[area_key] = {
            'on_track': on_track,
            'not_on_track': not_on_track,
            'percent_on_track': percent_on_track,
        }
    return summary
