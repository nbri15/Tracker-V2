#!/usr/bin/env python3
"""Backfill school_id values safely for multi-school stabilisation.

Rules:
- Demo data (username starts demo_, class name starts Demo, pupil first/last starts Demo, source='demo') => Demo School
- Everything else => Barrow School

Usage:
  python scripts/backfill_school_ids.py
"""

from __future__ import annotations

from sqlalchemy import text

from app import create_app
from app.extensions import db


RESULT_TABLES_WITH_PUPIL = [
    'subject_results',
    'writing_results',
    'foundation_results',
    'phonics_scores',
    'times_table_scores',
    'reception_tracker_entries',
    'sats_column_results',
    'sats_results',
    'sats_writing_results',
]

DIRECT_TABLES = [
    'interventions',
    'pupil_class_history',
]


def _ensure_school(name: str, slug: str, is_demo: bool) -> int:
    row = db.session.execute(text("SELECT id FROM schools WHERE slug = :slug LIMIT 1"), {'slug': slug}).scalar()
    if row:
        db.session.execute(
            text("UPDATE schools SET name = :name, is_active = TRUE, is_demo = :is_demo WHERE id = :id"),
            {'id': row, 'name': name, 'is_demo': is_demo},
        )
        return int(row)

    db.session.execute(
        text("INSERT INTO schools (name, slug, is_active, is_demo) VALUES (:name, :slug, TRUE, :is_demo)"),
        {'name': name, 'slug': slug, 'is_demo': is_demo},
    )
    return int(db.session.execute(text("SELECT id FROM schools WHERE slug = :slug LIMIT 1"), {'slug': slug}).scalar())


def _table_has_column(table_name: str, column_name: str) -> bool:
    query = text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
        """
    )
    return db.session.execute(query, {'table_name': table_name, 'column_name': column_name}).scalar() is not None


def main() -> None:
    app = create_app()

    with app.app_context():
        demo_school_id = _ensure_school('Demo School', 'demo-school', True)
        barrow_school_id = _ensure_school('Barrow School', 'barrow-school', False)
        db.session.commit()

        updated_counts: dict[str, int] = {}

        # Users
        demo_users = db.session.execute(
            text(
                """
                UPDATE users
                SET school_id = :demo_school_id
                WHERE lower(username) LIKE 'demo\\_%' ESCAPE '\\'
                """
            ),
            {'demo_school_id': demo_school_id},
        ).rowcount or 0
        barrow_users = db.session.execute(
            text(
                """
                UPDATE users
                SET school_id = :barrow_school_id
                WHERE school_id IS NULL
                   OR lower(username) NOT LIKE 'demo\\_%' ESCAPE '\\'
                """
            ),
            {'barrow_school_id': barrow_school_id},
        ).rowcount or 0
        updated_counts['users_demo'] = demo_users
        updated_counts['users_barrow'] = barrow_users

        # Classes
        demo_classes = db.session.execute(
            text("UPDATE school_classes SET school_id = :demo_school_id WHERE name ILIKE 'Demo%'"),
            {'demo_school_id': demo_school_id},
        ).rowcount or 0
        barrow_classes = db.session.execute(
            text("UPDATE school_classes SET school_id = :barrow_school_id WHERE school_id IS NULL OR name NOT ILIKE 'Demo%'"),
            {'barrow_school_id': barrow_school_id},
        ).rowcount or 0
        updated_counts['school_classes_demo'] = demo_classes
        updated_counts['school_classes_barrow'] = barrow_classes

        # Pupils
        demo_pupils = db.session.execute(
            text(
                """
                UPDATE pupils
                SET school_id = :demo_school_id
                WHERE first_name ILIKE 'Demo%'
                   OR last_name ILIKE 'Demo%'
                """
            ),
            {'demo_school_id': demo_school_id},
        ).rowcount or 0
        barrow_pupils = db.session.execute(
            text(
                """
                UPDATE pupils
                SET school_id = :barrow_school_id
                WHERE school_id IS NULL
                   OR (first_name NOT ILIKE 'Demo%' AND last_name NOT ILIKE 'Demo%')
                """
            ),
            {'barrow_school_id': barrow_school_id},
        ).rowcount or 0
        updated_counts['pupils_demo'] = demo_pupils
        updated_counts['pupils_barrow'] = barrow_pupils

        # Results tables via pupil_id
        for table_name in RESULT_TABLES_WITH_PUPIL:
            if not _table_has_column(table_name, 'school_id'):
                continue
            count = db.session.execute(
                text(
                    f"""
                    UPDATE {table_name} AS t
                    SET school_id = p.school_id
                    FROM pupils AS p
                    WHERE t.pupil_id = p.id
                    """
                )
            ).rowcount or 0
            updated_counts[f'{table_name}_via_pupil'] = count

            if _table_has_column(table_name, 'source'):
                source_demo_count = db.session.execute(
                    text(f"UPDATE {table_name} SET school_id = :demo_school_id WHERE lower(source) = 'demo'"),
                    {'demo_school_id': demo_school_id},
                ).rowcount or 0
                updated_counts[f'{table_name}_source_demo'] = source_demo_count

            null_fill_count = db.session.execute(
                text(f"UPDATE {table_name} SET school_id = :barrow_school_id WHERE school_id IS NULL"),
                {'barrow_school_id': barrow_school_id},
            ).rowcount or 0
            updated_counts[f'{table_name}_null_to_barrow'] = null_fill_count

        # Direct tables with pupil_id
        for table_name in DIRECT_TABLES:
            if not _table_has_column(table_name, 'school_id'):
                continue
            count = db.session.execute(
                text(
                    f"""
                    UPDATE {table_name} AS t
                    SET school_id = p.school_id
                    FROM pupils AS p
                    WHERE t.pupil_id = p.id
                    """
                )
            ).rowcount or 0
            updated_counts[f'{table_name}_via_pupil'] = count

            null_fill_count = db.session.execute(
                text(f"UPDATE {table_name} SET school_id = :barrow_school_id WHERE school_id IS NULL"),
                {'barrow_school_id': barrow_school_id},
            ).rowcount or 0
            updated_counts[f'{table_name}_null_to_barrow'] = null_fill_count

        db.session.commit()

        print('School ID backfill complete.')
        print(f'Demo School id: {demo_school_id}')
        print(f'Barrow School id: {barrow_school_id}')
        for key in sorted(updated_counts):
            print(f'{key}: {updated_counts[key]}')


if __name__ == '__main__':
    main()
