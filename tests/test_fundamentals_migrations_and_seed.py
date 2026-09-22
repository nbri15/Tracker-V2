"""Production-safety coverage for Fundamentals migrations and explicit seeding."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import (
    AcademicYear,
    FundamentalLevel,
    FundamentalPupilAttempt,
    FundamentalQuestion,
    FundamentalResponse,
    FundamentalSession,
    FundamentalStrand,
    Pupil,
    School,
    SchoolClass,
    User,
)
from config import config_by_name


FUNDAMENTALS_TABLES = {
    'fundamental_strands',
    'fundamental_levels',
    'fundamental_questions',
    'fundamental_sessions',
    'fundamental_pupil_attempts',
    'fundamental_responses',
}


def _make_app(database_path):
    config_key = f'fundamentals_test_{uuid4().hex}'

    class TestConfig:
        TESTING = True
        ENV = 'test'
        SECRET_KEY = 'migration-seed-test'
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{database_path}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        DEMO_MODE = False
        BOOTSTRAP_ADMIN_USERNAME = ''
        BOOTSTRAP_ADMIN_PASSWORD = ''

    config_by_name[config_key] = TestConfig
    try:
        return create_app(config_key)
    finally:
        config_by_name.pop(config_key, None)


@pytest.fixture(scope='module')
def migrated_app(tmp_path_factory):
    database_path = tmp_path_factory.mktemp('fundamentals-migrations') / 'test.db'
    app = _make_app(database_path)
    result = app.test_cli_runner().invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    return app


def test_normal_startup_does_not_create_alter_or_seed_schema(tmp_path, monkeypatch):
    database_path = tmp_path / 'startup.db'
    with sqlite3.connect(database_path) as connection:
        connection.execute('CREATE TABLE deployment_sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO deployment_sentinel (value) VALUES ('unchanged')")

    def fail_if_seeded(*args, **kwargs):
        raise AssertionError('Fundamentals seed ran during application startup')

    monkeypatch.setattr('app.fundamentals.seed.seed_fundamentals', fail_if_seeded)
    app = _make_app(database_path)

    with app.app_context():
        inspector = inspect(db.engine)
        assert inspector.get_table_names() == ['deployment_sentinel']
        assert [column['name'] for column in inspector.get_columns('deployment_sentinel')] == ['id', 'value']
        value = db.session.execute(text('SELECT value FROM deployment_sentinel')).scalar_one()
        assert value == 'unchanged'


def test_migrations_upgrade_a_clean_database_with_complete_fundamentals_schema(migrated_app):
    with migrated_app.app_context():
        inspector = inspect(db.engine)
        assert FUNDAMENTALS_TABLES <= set(inspector.get_table_names())
        response_columns = {column['name'] for column in inspector.get_columns('fundamental_responses')}
        assert {'question_text_snapshot', 'correct_answer_snapshot', 'skill_snapshot'} <= response_columns
        session_columns = {
            column['name']: column['nullable']
            for column in inspector.get_columns('fundamental_sessions')
        }
        assert session_columns['academic_year'] is True
        school_columns = {
            column['name']: column['nullable']
            for column in inspector.get_columns('schools')
        }
        assert school_columns['current_academic_year_id'] is False
        assert 'academic_year_reminder_dismissed_for' in school_columns

        nullable = {
            column['name']: column['nullable']
            for column in inspector.get_columns('fundamental_questions')
        }
        assert nullable['strand_id'] is False
        assert nullable['level_number'] is False
        assert nullable['question_id'] is False
        assert nullable['question_text'] is False
        assert nullable['answer'] is False
        assert {
            'skill', 'representation_type', 'mastery_focus',
            'rendering_notes', 'visual_data',
        } <= set(nullable)
        level_columns = {
            column['name']
            for column in inspector.get_columns('fundamental_levels')
        }
        assert {
            'diagnostic_intent', 'key_representations', 'mastery_emphasis',
        } <= level_columns

        question_fks = inspector.get_foreign_keys('fundamental_questions')
        assert any(
            fk['constrained_columns'] == ['strand_id']
            and fk['referred_table'] == 'fundamental_strands'
            for fk in question_fks
        )
        question_uniques = {
            tuple(item['column_names'])
            for item in inspector.get_unique_constraints('fundamental_questions')
        }
        assert ('strand_id', 'question_id') in question_uniques


def test_migration_adopts_existing_fundamentals_tables_without_losing_rows(tmp_path):
    database_path = tmp_path / 'adoption.db'
    app = _make_app(database_path)
    with app.app_context():
        db.create_all()
        db.session.execute(text(
            "INSERT INTO fundamental_strands (id, code, name) "
            "VALUES (901, 'LEGACY', 'Existing production strand')"
        ))
        db.session.commit()
        # Reproduce the schema created by startup before response snapshots
        # existed. These columns contain no data and are removed only in this
        # isolated test database.
        for column_name in ('question_text_snapshot', 'correct_answer_snapshot', 'skill_snapshot'):
            db.session.execute(text(f'ALTER TABLE fundamental_responses DROP COLUMN {column_name}'))
        db.session.commit()

    runner = app.test_cli_runner()
    stamped = runner.invoke(args=['db', 'stamp', '20260903_01'])
    assert stamped.exit_code == 0, stamped.output
    upgraded = runner.invoke(args=['db', 'upgrade'])
    assert upgraded.exit_code == 0, upgraded.output

    with app.app_context():
        strand = FundamentalStrand.query.filter_by(id=901).one()
        assert strand.code == 'LEGACY'
        response_columns = {
            column['name'] for column in inspect(db.engine).get_columns('fundamental_responses')
        }
        assert {'question_text_snapshot', 'correct_answer_snapshot', 'skill_snapshot'} <= response_columns


def test_explicit_seed_can_run_twice_and_creates_expected_bank(migrated_app):
    runner = migrated_app.test_cli_runner()
    first = runner.invoke(args=['fundamentals', 'seed'])
    assert first.exit_code == 0, first.output
    assert 'Strands: 3 created, 0 updated, 0 unchanged.' in first.output
    assert 'Levels: 47 created, 0 updated, 0 unchanged.' in first.output
    assert 'Questions: 1410 created, 0 updated, 0 unchanged.' in first.output

    second = runner.invoke(args=['fundamentals', 'seed'])
    assert second.exit_code == 0, second.output
    assert 'Strands: 0 created, 0 updated, 3 unchanged.' in second.output
    assert 'Levels: 0 created, 0 updated, 47 unchanged.' in second.output
    assert 'Questions: 0 created, 0 updated, 1410 unchanged.' in second.output

    with migrated_app.app_context():
        assert FundamentalStrand.query.count() == 3
        assert FundamentalLevel.query.count() == 47
        assert FundamentalQuestion.query.count() == 1410
        ens = FundamentalStrand.query.filter_by(code='ENS').one()
        nb = FundamentalStrand.query.filter_by(code='NB').one()
        pv = FundamentalStrand.query.filter_by(code='PV').one()
        assert FundamentalLevel.query.filter_by(strand_id=ens.id).count() == 15
        assert FundamentalQuestion.query.filter_by(strand_id=ens.id).count() == 450
        assert FundamentalLevel.query.filter_by(strand_id=nb.id).count() == 12
        assert FundamentalQuestion.query.filter_by(strand_id=nb.id).count() == 360
        assert FundamentalLevel.query.filter_by(strand_id=pv.id).count() == 20
        assert FundamentalQuestion.query.filter_by(strand_id=pv.id).count() == 600
        place_value_ids = {
            question.question_id
            for question in FundamentalQuestion.query.filter_by(strand_id=pv.id).all()
        }
        assert len(place_value_ids) == 600
        assert {'PV01-01', 'PV20-30'} <= place_value_ids
        visual = FundamentalQuestion.query.filter_by(strand_id=pv.id, question_id='PV03-01').one()
        assert visual.skill == 'Tens and ones / unitising'
        assert visual.representation_type == 'base ten'
        assert visual.mastery_focus == 'representation matching'
        assert visual.visual_data['blocks'] == {'ten': 8, 'one': 7}


def test_seed_updates_existing_question_instead_of_duplicating(migrated_app):
    with migrated_app.app_context():
        question = FundamentalQuestion.query.filter_by(question_id='ENS1-001').one()
        original_text = question.question_text
        question.question_text = 'outdated text'
        original_count = FundamentalQuestion.query.count()
        db.session.commit()

    result = migrated_app.test_cli_runner().invoke(args=['fundamentals', 'seed'])
    assert result.exit_code == 0, result.output
    assert 'Questions: 0 created, 1 updated, 1409 unchanged.' in result.output

    with migrated_app.app_context():
        assert FundamentalQuestion.query.count() == original_count
        question = FundamentalQuestion.query.filter_by(question_id='ENS1-001').one()
        assert question.question_text == original_text


def test_attempts_responses_and_snapshots_survive_reseeding(migrated_app):
    with migrated_app.app_context():
        academic_year = AcademicYear.query.filter_by(name='2025/26').one()
        school = School(
            name='Seed Safety School',
            slug='seed-safety-school',
            current_academic_year=academic_year,
        )
        db.session.add(school)
        db.session.flush()
        teacher = User(username='seed-safety-teacher', role='teacher', school_id=school.id)
        teacher.set_password('password123')
        db.session.add(teacher)
        db.session.flush()
        school_class = SchoolClass(
            name='Year 4',
            year_group=4,
            school_id=school.id,
            teacher_id=teacher.id,
        )
        db.session.add(school_class)
        db.session.flush()
        pupil = Pupil(
            school_id=school.id,
            first_name='Safe',
            last_name='Pupil',
            gender='Female',
            class_id=school_class.id,
        )
        db.session.add(pupil)
        db.session.flush()

        strand = FundamentalStrand.query.filter_by(code='ENS').one()
        question = FundamentalQuestion.query.filter_by(strand_id=strand.id, question_id='ENS1-001').one()
        level = FundamentalLevel.query.filter_by(strand_id=strand.id, level_number=1).one()
        session = FundamentalSession(
            school_class=school_class,
            teacher=teacher,
            strand=strand,
            start_level=1,
        )
        attempt = FundamentalPupilAttempt(session=session, pupil=pupil, current_level=1)
        response = FundamentalResponse(
            attempt=attempt,
            question=question,
            level_number=1,
            pupil_answer=question.answer,
            is_correct=True,
            question_text_snapshot=question.question_text,
            correct_answer_snapshot=question.answer,
            skill_snapshot=level.skill,
        )
        db.session.add_all([session, attempt, response])
        db.session.commit()
        attempt_id = attempt.id
        response_id = response.id
        snapshot = (
            response.question_text_snapshot,
            response.correct_answer_snapshot,
            response.skill_snapshot,
        )

    result = migrated_app.test_cli_runner().invoke(args=['fundamentals', 'seed'])
    assert result.exit_code == 0, result.output

    with migrated_app.app_context():
        assert FundamentalPupilAttempt.query.filter_by(id=attempt_id).one()
        response = FundamentalResponse.query.filter_by(id=response_id).one()
        assert (
            response.question_text_snapshot,
            response.correct_answer_snapshot,
            response.skill_snapshot,
        ) == snapshot
