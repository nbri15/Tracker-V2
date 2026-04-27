"""Admin setup, promotion, and history services."""

from __future__ import annotations

from dataclasses import dataclass

from app.extensions import db
from app.models import AcademicYear, Pupil, PupilClassHistory, School, SchoolClass, User
from .assessments import get_current_academic_year


@dataclass(frozen=True)
class DefaultLogin:
    username: str
    password: str
    role: str
    year_group: int | None = None


# NOTE: Default accounts below are for local development and test seeding only.
DEFAULT_ADMIN = DefaultLogin(username='admin', password='admin123', role='school_admin')
DEFAULT_TEACHERS = [DefaultLogin(username=f'teacher{year}', password=f'teacher{year}', role='teacher', year_group=year) for year in range(1, 7)]


def sort_teacher_accounts(users: list[User]) -> list[User]:
    def sort_key(user: User):
        suffix = ''.join(char for char in user.username if char.isdigit())
        suffix_value = int(suffix) if suffix else 999
        return (user.role not in {'school_admin', 'admin', 'executive_admin'}, suffix_value, user.username.lower())

    return sorted(users, key=sort_key)


def ensure_academic_year(name: str | None = None, *, mark_current: bool = False, archived: bool = False) -> AcademicYear:
    target_name = name or get_current_academic_year()
    record = AcademicYear.query.filter_by(name=target_name).first()
    if not record:
        record = AcademicYear(name=target_name)
    if mark_current:
        AcademicYear.query.update({'is_current': False})
        record.is_current = True
    if archived:
        record.is_archived = True
    db.session.add(record)
    db.session.flush()
    return record


def build_next_academic_year(academic_year: str) -> str:
    start_year = int(academic_year.split('/')[0]) + 1
    return f'{start_year}/{str(start_year + 1)[-2:]}'


def ensure_default_logins_and_classes() -> dict:
    ensure_academic_year(mark_current=True)
    default_school = School.query.filter_by(slug='barrow-school').first()
    if not default_school:
        default_school = School(name='Barrow School', slug='barrow-school', is_active=True, is_demo=False)
        db.session.add(default_school)
        db.session.flush()
    admin = User.query.filter_by(username=DEFAULT_ADMIN.username).first() or User(username=DEFAULT_ADMIN.username)
    admin.role = DEFAULT_ADMIN.role
    admin.legacy_is_admin = True
    admin.is_active = True
    admin.school_id = default_school.id
    admin.set_password(DEFAULT_ADMIN.password)
    db.session.add(admin)

    teachers: dict[int, User] = {}
    for login in DEFAULT_TEACHERS:
        teacher = User.query.filter_by(username=login.username).first() or User(username=login.username)
        teacher.username = login.username
        teacher.role = login.role
        teacher.legacy_is_admin = False
        teacher.is_active = True
        teacher.school_id = default_school.id
        teacher.set_password(login.password)
        db.session.add(teacher)
        db.session.flush()
        teachers[login.year_group] = teacher

    class_lookup = {}
    for year_group, teacher in teachers.items():
        name = f'Year {year_group}'
        school_class = SchoolClass.query.filter_by(name=name).first() or SchoolClass(name=name, year_group=year_group)
        school_class.name = name
        school_class.year_group = year_group
        school_class.teacher_id = teacher.id
        school_class.is_active = True
        school_class.school_id = default_school.id
        db.session.add(school_class)
        db.session.flush()
        class_lookup[year_group] = school_class

    reception_class = SchoolClass.query.filter_by(name='Reception').first() or SchoolClass(name='Reception', year_group=0)
    reception_class.name = 'Reception'
    reception_class.year_group = 0
    reception_class.is_active = True
    reception_class.school_id = default_school.id
    db.session.add(reception_class)
    db.session.flush()

    return {'admin': admin, 'teachers': teachers, 'classes': class_lookup, 'reception_class': reception_class}


def snapshot_pupil_history(academic_year: str) -> int:
    ensure_academic_year(academic_year)
    created = 0
    pupils = Pupil.query.join(Pupil.school_class).filter(Pupil.is_active.is_(True), SchoolClass.is_active.is_(True)).all()
    for pupil in pupils:
        existing = PupilClassHistory.query.filter_by(pupil_id=pupil.id, academic_year=academic_year).first()
        if existing:
            continue
        db.session.add(PupilClassHistory(
            pupil_id=pupil.id,
            academic_year=academic_year,
            class_name=pupil.school_class.name,
            year_group=pupil.school_class.year_group,
            teacher_username=pupil.school_class.teacher.username if pupil.school_class.teacher else None,
        ))
        created += 1
    db.session.flush()
    return created


def get_promotion_mapping_options() -> list[dict]:
    """Build source-class rows and valid destination options for promotion UI."""
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all()
    options: list[dict] = []
    for school_class in classes:
        active_pupil_count = school_class.pupils.filter_by(is_active=True).count()
        destination_classes = (
            SchoolClass.query.filter_by(is_active=True, year_group=school_class.year_group + 1)
            .order_by(SchoolClass.name)
            .all()
        )
        options.append({
            'source_class': school_class,
            'active_pupil_count': active_pupil_count,
            'destination_classes': destination_classes,
            'requires_selection': bool(destination_classes),
            'default_destination_id': destination_classes[0].id if len(destination_classes) == 1 else None,
        })
    return options


def promote_pupils_to_next_year(source_year: str, class_mapping: dict[int, int | None] | None = None) -> dict:
    snapshot_count = snapshot_pupil_history(source_year)
    target_year = build_next_academic_year(source_year)
    ensure_academic_year(source_year, archived=True)
    ensure_academic_year(target_year, mark_current=True)

    normalized_mapping = class_mapping or {}
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group.desc(), SchoolClass.name).all()
    moved = 0
    leavers = 0
    for school_class in classes:
        pupils = school_class.pupils.filter_by(is_active=True).all()
        selected_destination_id = normalized_mapping.get(school_class.id)
        selected_destination = None
        if selected_destination_id:
            selected_destination = SchoolClass.query.filter_by(id=selected_destination_id, is_active=True).first()
            if not selected_destination:
                raise ValueError(f'Invalid destination selected for {school_class.name}.')
            if selected_destination.year_group != school_class.year_group + 1:
                raise ValueError(f'Invalid destination year group selected for {school_class.name}.')
        for pupil in pupils:
            history = PupilClassHistory.query.filter_by(pupil_id=pupil.id, academic_year=source_year).first()
            if selected_destination is None and school_class.year_group >= 6:
                pupil.is_active = False
                leavers += 1
                if history:
                    history.promoted_to_year_group = None
                    db.session.add(history)
                db.session.add(pupil)
                continue
            next_class = selected_destination
            if not next_class:
                next_class = SchoolClass.query.filter_by(year_group=school_class.year_group + 1, is_active=True).order_by(SchoolClass.name).first()
                if not next_class:
                    next_class = SchoolClass(name=f'Year {school_class.year_group + 1}', year_group=school_class.year_group + 1, is_active=True)
                    db.session.add(next_class)
                    db.session.flush()
            pupil.class_id = next_class.id
            moved += 1
            if history:
                history.promoted_to_year_group = next_class.year_group
                db.session.add(history)
            db.session.add(pupil)
    db.session.flush()
    return {'snapshot_count': snapshot_count, 'moved': moved, 'leavers': leavers, 'target_year': target_year}


def get_history_rows(academic_year: str) -> list[PupilClassHistory]:
    return (
        PupilClassHistory.query.join(PupilClassHistory.pupil)
        .filter(PupilClassHistory.academic_year == academic_year)
        .order_by(PupilClassHistory.year_group, PupilClassHistory.class_name, Pupil.last_name, Pupil.first_name)
        .all()
    )
