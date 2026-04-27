#!/usr/bin/env python3
"""Repair cross-school data assignments after multi-school migration.

Usage:
  python scripts/fix_school_assignments.py
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import School

TARGET_TABLES = [
    'schools',
    'users',
    'school_classes',
    'pupils',
    'subject_results',
    'writing_results',
    'interventions',
    'foundation_results',
    'phonics_scores',
    'times_table_scores',
    'reception_tracker_entries',
    'sats_exam_tabs',
    'sats_column_results',
    'sats_column_settings',
    'sats_results',
    'sats_writing_results',
    'tracker_mode_settings',
    'academic_years',
    'assessment_settings',
    'gap_templates',
    'gap_questions',
    'gap_scores',
    'pupil_class_history',
]


def has_table(inspector, table: str) -> bool:
    return inspector.has_table(table)


def has_column(inspector, table: str, column: str) -> bool:
    if not has_table(inspector, table):
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def resolve_school_ids() -> tuple[int, int]:
    barrow = School.query.filter_by(slug='barrow-school').first()
    demo = School.query.filter_by(slug='demo-school').first()

    if not barrow:
        barrow = School.query.get(1)
    if not demo:
        demo = School.query.get(2)

    if not barrow or not demo:
        raise RuntimeError('Unable to resolve Barrow/Demo schools by slug or fallback ids (1/2).')

    return barrow.id, demo.id


def update(connection, sql: str, **params) -> int:
    return connection.execute(text(sql), params).rowcount or 0


def main() -> None:
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        barrow_id, demo_id = resolve_school_ids()
        updates: dict[str, int] = defaultdict(int)

        with db.engine.begin() as connection:
            # 1) Users
            if has_table(inspector, 'users') and has_column(inspector, 'users', 'school_id'):
                updates['users'] += update(
                    connection,
                    """
                    UPDATE users
                    SET school_id = :demo_id,
                        is_demo = TRUE
                    WHERE lower(username) LIKE 'demo\_%' ESCAPE '\\'
                    """,
                    demo_id=demo_id,
                )
                updates['users'] += update(
                    connection,
                    """
                    UPDATE users
                    SET school_id = :barrow_id,
                        is_demo = FALSE
                    WHERE role <> 'executive_admin'
                      AND lower(username) NOT LIKE 'demo\_%' ESCAPE '\\'
                      AND (school_id IS NULL OR school_id IN (:barrow_id, :demo_id))
                    """,
                    barrow_id=barrow_id,
                    demo_id=demo_id,
                )
                updates['users'] += update(
                    connection,
                    """
                    UPDATE users
                    SET school_id = NULL
                    WHERE role = 'executive_admin'
                    """,
                )

            # 2) Classes
            if has_table(inspector, 'school_classes') and has_column(inspector, 'school_classes', 'school_id'):
                updates['school_classes'] += update(
                    connection,
                    """
                    UPDATE school_classes
                    SET school_id = :demo_id,
                        is_demo = TRUE
                    WHERE name ILIKE 'Demo%'
                    """,
                    demo_id=demo_id,
                )
                updates['school_classes'] += update(
                    connection,
                    """
                    UPDATE school_classes
                    SET school_id = :barrow_id,
                        is_demo = FALSE
                    WHERE name NOT ILIKE 'Demo%'
                      AND (school_id IS NULL OR school_id IN (:barrow_id, :demo_id))
                    """,
                    barrow_id=barrow_id,
                    demo_id=demo_id,
                )

            # 3) Pupils
            pupil_demo_conditions = ["p.first_name ILIKE 'Demo%'"]
            if has_column(inspector, 'pupils', 'name'):
                pupil_demo_conditions.append("p.name ILIKE 'Demo%'")
            if has_column(inspector, 'pupils', 'class_id'):
                pupil_demo_conditions.append("c.name ILIKE 'Demo%'")
            pupil_demo_sql = ' OR '.join(pupil_demo_conditions)

            if has_table(inspector, 'pupils') and has_column(inspector, 'pupils', 'school_id'):
                updates['pupils'] += update(
                    connection,
                    f"""
                    UPDATE pupils p
                    SET school_id = :demo_id,
                        is_demo = TRUE
                    FROM school_classes c
                    WHERE p.class_id = c.id
                      AND ({pupil_demo_sql})
                    """,
                    demo_id=demo_id,
                )
                updates['pupils'] += update(
                    connection,
                    f"""
                    UPDATE pupils p
                    SET school_id = :barrow_id,
                        is_demo = FALSE
                    FROM school_classes c
                    WHERE p.class_id = c.id
                      AND NOT ({pupil_demo_sql})
                      AND (p.school_id IS NULL OR p.school_id IN (:barrow_id, :demo_id))
                    """,
                    barrow_id=barrow_id,
                    demo_id=demo_id,
                )

            # 4) Pupil-linked tables adopt school from pupil.
            pupil_linked = [
                'subject_results',
                'writing_results',
                'interventions',
                'foundation_results',
                'phonics_scores',
                'times_table_scores',
                'reception_tracker_entries',
                'sats_column_results',
                'sats_results',
                'sats_writing_results',
                'gap_scores',
                'pupil_class_history',
            ]

            for table in pupil_linked:
                if not (has_table(inspector, table) and has_column(inspector, table, 'school_id') and has_column(inspector, table, 'pupil_id')):
                    continue
                updates[table] += update(
                    connection,
                    f"""
                    UPDATE {table} t
                    SET school_id = p.school_id
                    FROM pupils p
                    WHERE t.pupil_id = p.id
                      AND p.school_id IS NOT NULL
                      AND t.school_id IS DISTINCT FROM p.school_id
                    """,
                )

                if table in {'subject_results', 'writing_results'} and has_column(inspector, table, 'source'):
                    updates[table] += update(
                        connection,
                        f"""
                        UPDATE {table}
                        SET school_id = :demo_id
                        WHERE lower(coalesce(source, '')) = 'demo'
                        """,
                        demo_id=demo_id,
                    )

            # 5) Remaining school-scoped tables: assign demo by source/name if possible, then fill NULLs to Barrow.
            for table in TARGET_TABLES:
                if table in {'schools', 'users', 'school_classes', 'pupils'} | set(pupil_linked):
                    continue
                if not (has_table(inspector, table) and has_column(inspector, table, 'school_id')):
                    continue

                if has_column(inspector, table, 'source'):
                    updates[table] += update(
                        connection,
                        f"""
                        UPDATE {table}
                        SET school_id = :demo_id
                        WHERE lower(coalesce(source, '')) = 'demo'
                        """,
                        demo_id=demo_id,
                    )
                if has_column(inspector, table, 'name'):
                    updates[table] += update(
                        connection,
                        f"""
                        UPDATE {table}
                        SET school_id = :demo_id
                        WHERE name ILIKE 'Demo%'
                          AND (school_id IS NULL OR school_id IN (:barrow_id, :demo_id))
                        """,
                        demo_id=demo_id,
                        barrow_id=barrow_id,
                    )

                updates[table] += update(
                    connection,
                    f"""
                    UPDATE {table}
                    SET school_id = :barrow_id
                    WHERE school_id IS NULL
                    """,
                    barrow_id=barrow_id,
                )

        # Reporting
        barrow_classes = db.session.execute(text('SELECT count(*) FROM school_classes WHERE school_id = :sid'), {'sid': barrow_id}).scalar_one()
        demo_classes = db.session.execute(text('SELECT count(*) FROM school_classes WHERE school_id = :sid'), {'sid': demo_id}).scalar_one()
        barrow_pupils = db.session.execute(text('SELECT count(*) FROM pupils WHERE school_id = :sid'), {'sid': barrow_id}).scalar_one()
        demo_pupils = db.session.execute(text('SELECT count(*) FROM pupils WHERE school_id = :sid'), {'sid': demo_id}).scalar_one()

        users_by_school = db.session.execute(
            text(
                """
                SELECT coalesce(cast(school_id as text), 'NULL') as school_key, count(*)
                FROM users
                GROUP BY school_key
                ORDER BY school_key
                """
            )
        ).all()

        print('School assignment repair complete')
        print(f'Barrow school id: {barrow_id}')
        print(f'Demo school id: {demo_id}')
        print(f'Barrow classes count: {barrow_classes}')
        print(f'Barrow pupils count: {barrow_pupils}')
        print(f'Demo classes count: {demo_classes}')
        print(f'Demo pupils count: {demo_pupils}')
        print('Users by school:')
        for school_key, count in users_by_school:
            print(f'  school_id={school_key}: {count}')
        print('Rows updated per table:')
        for table in sorted(updates):
            print(f'  {table}: {updates[table]}')


if __name__ == '__main__':
    main()
