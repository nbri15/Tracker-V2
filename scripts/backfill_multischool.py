#!/usr/bin/env python3
"""Safe idempotent backfill for multi-school tenancy and role split.

Usage:
  python scripts/backfill_multischool.py
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import School, User

REAL_SCHOOL = {'name': 'Barrow School', 'slug': 'barrow-school', 'is_demo': False}
DEMO_SCHOOL = {'name': 'Demo School', 'slug': 'demo-school', 'is_demo': True}

SCHOOL_ID_TABLES = [
    'users',
    'school_classes',
    'pupils',
    'academic_years',
    'term_configs',
    'assessment_settings',
    'subject_results',
    'writing_results',
    'interventions',
    'sats_exam_tabs',
    'sats_column_results',
    'sats_results',
    'sats_writing_results',
    'pupil_profiles',
    'pupil_report_notes',
    'paper_templates',
    'reception_tracker_entries',
    'foundation_results',
    'phonics_test_columns',
    'phonics_scores',
    'times_table_test_columns',
    'times_table_scores',
    'gap_templates',
    'gap_questions',
    'gap_scores',
    'pupil_class_history',
]


def _has_table(inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def _ensure_school(name: str, slug: str, is_demo: bool) -> School:
    school = School.query.filter_by(slug=slug).first()
    if school:
        changed = False
        if school.name != name:
            school.name = name
            changed = True
        if school.is_demo != is_demo:
            school.is_demo = is_demo
            changed = True
        if not school.is_active:
            school.is_active = True
            changed = True
        if changed:
            db.session.add(school)
        return school

    school = School(name=name, slug=slug, is_demo=is_demo, is_active=True)
    db.session.add(school)
    db.session.flush()
    return school


def _backfill_school_ids(barrow_id: int, demo_id: int) -> None:
    inspector = inspect(db.engine)
    with db.engine.begin() as connection:
        for table_name in SCHOOL_ID_TABLES:
            if not _has_column(inspector, table_name, 'school_id'):
                continue

            has_is_demo = _has_column(inspector, table_name, 'is_demo')
            has_username = _has_column(inspector, table_name, 'username')
            has_name = _has_column(inspector, table_name, 'name')
            has_first_name = _has_column(inspector, table_name, 'first_name')
            has_last_name = _has_column(inspector, table_name, 'last_name')
            has_source = _has_column(inspector, table_name, 'source')

            if has_is_demo:
                connection.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND is_demo = TRUE"),
                    {'demo_id': demo_id},
                )

            if has_username:
                connection.execute(
                    text(
                        f"UPDATE {table_name} SET school_id = :demo_id "
                        "WHERE school_id IS NULL AND lower(username) LIKE 'demo\\_%' ESCAPE '\\'"
                    ),
                    {'demo_id': demo_id},
                )

            if has_name:
                connection.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND name ILIKE 'Demo%'"),
                    {'demo_id': demo_id},
                )

            if has_first_name:
                connection.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND first_name ILIKE 'Demo%'"),
                    {'demo_id': demo_id},
                )

            if has_last_name:
                connection.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND last_name ILIKE 'Demo%'"),
                    {'demo_id': demo_id},
                )

            if has_source:
                connection.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_id WHERE school_id IS NULL AND lower(source) = 'demo'"),
                    {'demo_id': demo_id},
                )

            connection.execute(
                text(f"UPDATE {table_name} SET school_id = :barrow_id WHERE school_id IS NULL"),
                {'barrow_id': barrow_id},
            )


def _set_user_defaults(barrow: School, demo: School) -> None:
    owner = User.query.filter_by(username='owner').first()
    if not owner:
        owner = User(username='owner', is_active=True, is_demo=False)
    owner.role = 'executive_admin'
    owner.school_id = None
    owner.is_demo = False
    owner.set_password('Owner123!')
    owner.require_password_change = False
    if hasattr(owner, 'legacy_is_admin'):
        owner.legacy_is_admin = True
    db.session.add(owner)

    admin = User.query.filter_by(username='admin').first()
    if admin and admin.username != 'owner':
        if admin.role != 'executive_admin':
            admin.role = 'school_admin'
            admin.school_id = barrow.id
            admin.is_demo = False
            if hasattr(admin, 'legacy_is_admin'):
                admin.legacy_is_admin = True
            db.session.add(admin)

    demo_admin = User.query.filter_by(username='demo_admin').first()
    if not demo_admin:
        demo_admin = User(username='demo_admin', is_active=True)
        demo_admin.set_password('demo123')
    demo_admin.role = 'school_admin'
    demo_admin.school_id = demo.id
    demo_admin.is_demo = True
    if hasattr(demo_admin, 'legacy_is_admin'):
        demo_admin.legacy_is_admin = True
    db.session.add(demo_admin)

    demo_teacher = User.query.filter_by(username='demo_teacher').first()
    if not demo_teacher:
        demo_teacher = User(username='demo_teacher', is_active=True)
        demo_teacher.set_password('demo123')
    demo_teacher.role = 'teacher'
    demo_teacher.school_id = demo.id
    demo_teacher.is_demo = True
    if hasattr(demo_teacher, 'legacy_is_admin'):
        demo_teacher.legacy_is_admin = False
    db.session.add(demo_teacher)


def main() -> None:
    app = create_app()
    with app.app_context():
        barrow = _ensure_school(**REAL_SCHOOL)
        demo = _ensure_school(**DEMO_SCHOOL)
        db.session.commit()

        _backfill_school_ids(barrow.id, demo.id)

        _set_user_defaults(barrow, demo)
        db.session.commit()

        print('Multi-school backfill complete.')
        print(f"- Barrow School id={barrow.id}")
        print(f"- Demo School id={demo.id}")
        print('- Executive admin: owner / Owner123!')


if __name__ == '__main__':
    main()
