from datetime import datetime, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AcademicYear,
    FundamentalLevel,
    FundamentalSession,
    FundamentalStrand,
    Pupil,
    School,
    SchoolClass,
    SubjectResult,
    User,
)
from app.services import (
    get_school_working_academic_year,
    promote_pupils_to_next_year,
    should_show_academic_year_reminder,
)
from config import Config, config_by_name


def _make_app(tmp_path, monkeypatch, name='academic-year-test'):
    class AcademicYearTestConfig(Config):
        TESTING = True
        ENV = 'testing'
        SECRET_KEY = 'academic-year-test-key'
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / f'{name}.db'}"
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        DEMO_MODE = False

    monkeypatch.setitem(config_by_name, name, AcademicYearTestConfig)
    return create_app(name)


def _seed_school(app, *, second_school=False):
    with app.app_context():
        old_year = AcademicYear(name='2025/26', is_current=False)
        next_year = AcademicYear(name='2026/27', is_current=True)
        school = School(name='School A', slug='school-a', current_academic_year=old_year)
        admin = User(username='admin-a', role='school_admin', school=school, is_active=True)
        admin.set_password('password123')
        year4 = SchoolClass(name='Year 4', year_group=4, school=school, is_active=True)
        year5 = SchoolClass(name='Year 5', year_group=5, school=school, is_active=True)
        db.session.add_all([old_year, next_year, school, admin, year4, year5])
        db.session.flush()
        pupil = Pupil(
            school_id=school.id,
            school_class=year4,
            first_name='Alice',
            last_name='Example',
            gender='Female',
            is_active=True,
        )
        result = SubjectResult(
            school_id=school.id,
            pupil=pupil,
            academic_year='2025/26',
            term='autumn',
            subject='maths',
        )
        db.session.add_all([pupil, result])
        school_b = None
        if second_school:
            school_b = School(name='School B', slug='school-b', current_academic_year=next_year)
            class_b = SchoolClass(name='B Year 4', year_group=4, school=school_b, is_active=True)
            db.session.add_all([school_b, class_b])
            db.session.flush()
            pupil_b = Pupil(
                school_id=school_b.id,
                school_class=class_b,
                first_name='Bob',
                last_name='Example',
                gender='Male',
                is_active=True,
            )
            db.session.add(pupil_b)
        db.session.commit()
        return {
            'school': school.id,
            'admin': admin.id,
            'year4': year4.id,
            'year5': year5.id,
            'pupil': pupil.id,
            'result': result.id,
            'school_b': school_b.id if school_b else None,
        }


def _login(client, user_id):
    with client.session_transaction() as flask_session:
        flask_session['_user_id'] = str(user_id)
        flask_session['_fresh'] = True


def test_september_uses_stored_year_and_only_offers_next_stored_year(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'stored-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)

    fixed_date = datetime(2026, 9, 15, tzinfo=timezone.utc)
    with app.app_context():
        school = db.session.get(School, ids['school'])
        assert get_school_working_academic_year(school.id).name == '2025/26'
        assert should_show_academic_year_reminder(school, fixed_date) is True
        assert should_show_academic_year_reminder(
            school, datetime(2026, 10, 1, tzinfo=timezone.utc)
        ) is False

    monkeypatch.setattr('app.dashboards.routes.get_current_academic_year', lambda: '2026/27')
    monkeypatch.setattr('app.dashboards.routes.should_show_academic_year_reminder', lambda school: True)
    client = app.test_client()
    _login(client, ids['admin'])
    dashboard = client.get('/dashboard/admin')
    assert dashboard.status_code == 200
    text = dashboard.get_data(as_text=True)
    assert 'academic year 2025/26' in text

    promotion = client.get('/admin/promotion')
    promotion_text = promotion.get_data(as_text=True)
    assert 'promote pupils from 2025/26 into 2026/27' in promotion_text
    assert '2027/28' not in promotion_text


def test_keep_current_year_dismisses_reminder_without_changing_cohorts(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'dismiss-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)
    monkeypatch.setattr('app.admin.routes.get_current_academic_year', lambda: '2026/27')

    client = app.test_client()
    _login(client, ids['admin'])
    response = client.post('/admin/academic-year/reminder/dismiss', data={'reminder_year': '2026/27'})
    assert response.status_code == 302

    with app.app_context():
        school = db.session.get(School, ids['school'])
        pupil = db.session.get(Pupil, ids['pupil'])
        assert school.current_academic_year.name == '2025/26'
        assert school.academic_year_reminder_dismissed_for == '2026/27'
        assert pupil.class_id == ids['year4']
        assert should_show_academic_year_reminder(
            school, datetime(2026, 9, 15, tzinfo=timezone.utc)
        ) is False


def test_manual_year_change_does_not_promote_or_rewrite_assessments(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'manual-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)

    client = app.test_client()
    _login(client, ids['admin'])
    response = client.post('/admin/settings', data={
        'action': 'set-active-academic-year',
        'expected_academic_year': '2025/26',
        'academic_year': '2026/27',
        'confirm_academic_year_change': 'yes',
    })
    assert response.status_code == 302

    with app.app_context():
        school = db.session.get(School, ids['school'])
        pupil = db.session.get(Pupil, ids['pupil'])
        result = db.session.get(SubjectResult, ids['result'])
        assert school.current_academic_year.name == '2026/27'
        assert pupil.class_id == ids['year4']
        assert result.academic_year == '2025/26'


def test_explicit_rollover_advances_once_and_preserves_history(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'rollover-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)

    with app.app_context():
        outcome = promote_pupils_to_next_year(
            '2025/26',
            ids['school'],
            class_mapping={ids['year4']: ids['year5'], ids['year5']: None},
        )
        db.session.commit()
        assert outcome['target_year'] == '2026/27'
        assert db.session.get(School, ids['school']).current_academic_year.name == '2026/27'
        assert db.session.get(Pupil, ids['pupil']).class_id == ids['year5']
        assert db.session.get(SubjectResult, ids['result']).academic_year == '2025/26'

        with pytest.raises(ValueError, match='already working in 2026/27'):
            promote_pupils_to_next_year('2025/26', ids['school'])
        db.session.rollback()
        assert db.session.get(Pupil, ids['pupil']).class_id == ids['year5']


def test_two_schools_keep_independent_years_and_cohorts(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'multi-school-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app, second_school=True)

    with app.app_context():
        school_b = db.session.get(School, ids['school_b'])
        pupil_b = Pupil.query.filter_by(school_id=school_b.id).one()
        original_b_class = pupil_b.class_id
        promote_pupils_to_next_year(
            '2025/26',
            ids['school'],
            class_mapping={ids['year4']: ids['year5'], ids['year5']: None},
        )
        db.session.commit()
        assert db.session.get(School, ids['school']).current_academic_year.name == '2026/27'
        assert school_b.current_academic_year.name == '2026/27'
        assert pupil_b.class_id == original_b_class


def test_application_restart_never_changes_stored_year(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'restart-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    class RestartConfig(Config):
        TESTING = True
        SECRET_KEY = 'restart-test-key'
        SQLALCHEMY_DATABASE_URI = db_uri
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False

    monkeypatch.setitem(config_by_name, 'restart-second-app', RestartConfig)
    restarted_app = create_app('restart-second-app')
    with restarted_app.app_context():
        assert db.session.get(School, ids['school']).current_academic_year.name == '2025/26'


def test_fundamentals_session_snapshots_school_stored_year(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, 'fundamentals-year')
    with app.app_context():
        db.create_all()
    ids = _seed_school(app)
    with app.app_context():
        admin = db.session.get(User, ids['admin'])
        school_class = db.session.get(SchoolClass, ids['year4'])
        school_class.teacher = admin
        strand = FundamentalStrand(code='TEST', name='Test strand')
        level = FundamentalLevel(strand=strand, level_number=1, skill='Test skill', pass_mark=70)
        db.session.add_all([school_class, strand, level])
        db.session.commit()
        strand_id = strand.id

    client = app.test_client()
    _login(client, ids['admin'])
    response = client.post('/fundamentals/start', data={
        'class_id': ids['year4'],
        'strand_id': strand_id,
        'start_level': 1,
    })
    assert response.status_code == 302
    with app.app_context():
        session = FundamentalSession.query.one()
        assert session.academic_year == '2025/26'
