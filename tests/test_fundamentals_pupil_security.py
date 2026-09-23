import html
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest
from itsdangerous import URLSafeTimedSerializer

from app import create_app
from app.extensions import db
from app.fundamentals import routes as fundamentals_routes
from app.fundamentals.seed import seed_fundamentals
from app.models import (
    AcademicYear,
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
from config import Config, config_by_name


def _hidden_value(response, name):
    match = re.search(
        rf'name="{re.escape(name)}" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match, f'Missing hidden form value: {name}'
    return html.unescape(match.group(1))


def _login(client, user_id):
    with client.session_transaction() as flask_session:
        flask_session['_user_id'] = str(user_id)
        flask_session['_fresh'] = True


@pytest.fixture()
def fundamentals_app(tmp_path, monkeypatch):
    class FundamentalsTestConfig(Config):
        TESTING = True
        ENV = 'testing'
        SECRET_KEY = 'fundamentals-security-test-key'
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'fundamentals.db'}"
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = True
        FUNDAMENTALS_TOKEN_MAX_AGE = 3600

    monkeypatch.setitem(config_by_name, 'fundamentals-security-test', FundamentalsTestConfig)
    app = create_app('fundamentals-security-test')

    with app.app_context():
        db.create_all()
        seed_fundamentals()
        academic_year = AcademicYear(name='2025/26', is_current=True)
        db.session.add(academic_year)
        db.session.flush()
        school_a = School(name='School A', slug='school-a', current_academic_year=academic_year)
        school_b = School(name='School B', slug='school-b', current_academic_year=academic_year)
        db.session.add_all([school_a, school_b])
        db.session.flush()

        teacher_a = User(username='teacher-a', role='teacher', school_id=school_a.id, is_active=True)
        teacher_a.set_password('password123')
        teacher_b = User(username='teacher-b', role='teacher', school_id=school_b.id, is_active=True)
        teacher_b.set_password('password123')
        db.session.add_all([teacher_a, teacher_b])
        db.session.flush()

        class_a = SchoolClass(name='A Year 3', year_group=3, school_id=school_a.id, teacher_id=teacher_a.id)
        class_b = SchoolClass(name='B Year 3', year_group=3, school_id=school_b.id, teacher_id=teacher_b.id)
        db.session.add_all([class_a, class_b])
        db.session.flush()

        pupil_a = Pupil(first_name='Alice', last_name='Alpha', gender='Female', school_id=school_a.id, class_id=class_a.id)
        pupil_b = Pupil(first_name='Ben', last_name='Beta', gender='Male', school_id=school_b.id, class_id=class_b.id)
        db.session.add_all([pupil_a, pupil_b])
        db.session.flush()

        ens = FundamentalStrand.query.filter_by(code='ENS').one()
        nb = FundamentalStrand.query.filter_by(code='NB').one()
        pv = FundamentalStrand.query.filter_by(code='PV').one()
        sessions = {
            'a_ens': FundamentalSession(class_id=class_a.id, teacher_id=teacher_a.id, strand_id=ens.id, start_level=1),
            'a_nb': FundamentalSession(class_id=class_a.id, teacher_id=teacher_a.id, strand_id=nb.id, start_level=1),
            'a_pv': FundamentalSession(class_id=class_a.id, teacher_id=teacher_a.id, strand_id=pv.id, start_level=1, academic_year='2025/26'),
            'b_ens': FundamentalSession(class_id=class_b.id, teacher_id=teacher_b.id, strand_id=ens.id, start_level=1),
        }
        db.session.add_all(sessions.values())
        db.session.commit()

        app.config['FUNDAMENTALS_TEST_IDS'] = {
            'teacher_a': teacher_a.id,
            'class_a': class_a.id,
            'class_b': class_b.id,
            'pupil_a': pupil_a.id,
            'pupil_b': pupil_b.id,
            'a_ens': sessions['a_ens'].id,
            'a_nb': sessions['a_nb'].id,
            'a_pv': sessions['a_pv'].id,
            'b_ens': sessions['b_ens'].id,
        }

    return app


def _session_join_path(app, session_key):
    with app.app_context():
        session_id = app.config['FUNDAMENTALS_TEST_IDS'][session_key]
        session = db.session.get(FundamentalSession, session_id)
        token = fundamentals_routes.make_session_token(session)
        return f'/fundamentals/join/{token}'


def _start_attempt(client, join_path, pupil_id):
    join_page = client.get(join_path)
    csrf_token = _hidden_value(join_page, 'csrf_token')
    return client.post(
        join_path,
        data={'csrf_token': csrf_token, 'pupil_id': pupil_id},
        follow_redirects=False,
    )


def test_session_qr_is_exact_and_school_scoped(fundamentals_app, monkeypatch):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    _login(client, ids['teacher_a'])
    captured_urls = []

    class FakeQrImage:
        def save(self, stream, image_format):
            assert image_format == 'PNG'
            stream.write(b'fake-png')

    def capture_qr(url):
        captured_urls.append(url)
        return FakeQrImage()

    monkeypatch.setattr(fundamentals_routes.qrcode, 'make', capture_qr)

    assert client.get('/fundamentals/pupil').status_code == 404
    assert client.get(f"/fundamentals/api/classes/{ids['class_b']}/pupils").status_code == 404

    assert client.get(f"/fundamentals/qr/{ids['a_ens']}").status_code == 200
    ens_page = client.get(urlsplit(captured_urls[-1]).path)
    ens_body = ens_page.get_data(as_text=True)
    assert ens_page.status_code == 200
    assert 'Early Number Sense' in ens_body
    assert 'A Year 3' in ens_body
    assert 'Alice Alpha' in ens_body
    assert 'B Year 3' not in ens_body
    assert 'Ben Beta' not in ens_body

    assert client.get(f"/fundamentals/qr/{ids['a_nb']}").status_code == 200
    nb_page = client.get(urlsplit(captured_urls[-1]).path)
    nb_body = nb_page.get_data(as_text=True)
    assert nb_page.status_code == 200
    assert 'Number Bonds' in nb_body
    assert 'Alice Alpha' in nb_body
    assert 'Ben Beta' not in nb_body
    assert captured_urls[-1] != captured_urls[-2]

    assert client.get(f"/fundamentals/qr/{ids['a_pv']}").status_code == 200
    pv_page = client.get(urlsplit(captured_urls[-1]).path)
    pv_body = pv_page.get_data(as_text=True)
    assert pv_page.status_code == 200
    assert 'Place Value' in pv_body
    assert 'Alice Alpha' in pv_body
    assert 'Ben Beta' not in pv_body


def test_cross_school_pupil_and_attempt_are_rejected(fundamentals_app):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    school_a_join = _session_join_path(fundamentals_app, 'a_ens')

    cross_school_start = _start_attempt(client, school_a_join, ids['pupil_b'])
    assert cross_school_start.status_code == 404

    with fundamentals_app.app_context():
        session_b = db.session.get(FundamentalSession, ids['b_ens'])
        invalid_attempt = FundamentalPupilAttempt(
            session_id=session_b.id,
            pupil_id=ids['pupil_a'],
            current_level=session_b.start_level,
        )
        db.session.add(invalid_attempt)
        db.session.commit()
        invalid_token = fundamentals_routes.make_attempt_token(invalid_attempt)

    response = client.get(f'/fundamentals/pupil/question/{invalid_token}')
    assert response.status_code == 404


def test_normal_submission_uses_csrf_and_duplicate_is_idempotent(fundamentals_app):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    join_path = _session_join_path(fundamentals_app, 'a_ens')

    start_response = _start_attempt(client, join_path, ids['pupil_a'])
    assert start_response.status_code == 302
    assert '/fundamentals/pupil/question/' in start_response.location

    question_path = urlsplit(start_response.location).path
    question_page = client.get(question_path)
    csrf_token = _hidden_value(question_page, 'csrf_token')
    question_token = _hidden_value(question_page, 'question_token')
    form_data = {
        'csrf_token': csrf_token,
        'question_token': question_token,
        'answer': '1',
    }

    first = client.post(question_path, data=form_data, follow_redirects=False)
    second = client.post(question_path, data=form_data, follow_redirects=False)
    assert first.status_code == 302
    assert second.status_code == 302

    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(
            session_id=ids['a_ens'],
            pupil_id=ids['pupil_a'],
        ).one()
        assert FundamentalResponse.query.filter_by(attempt_id=attempt.id).count() == 1
        assert attempt.current_level == 1
        assert attempt.below_70_streak == 0


def _submit_level(app, client, question_path, correct_answers):
    for answer_index in range(10):
        question_page = client.get(question_path)
        assert question_page.status_code == 200
        csrf_token = _hidden_value(question_page, 'csrf_token')
        question_token = _hidden_value(question_page, 'question_token')
        with app.app_context():
            payload = URLSafeTimedSerializer(
                app.config['SECRET_KEY'],
                signer_kwargs={'digest_method': hashlib.sha256},
            ).loads(
                question_token,
                salt=fundamentals_routes.QUESTION_TOKEN_SALT,
                max_age=app.config['FUNDAMENTALS_TOKEN_MAX_AGE'],
            )
            question = db.session.get(FundamentalQuestion, payload['question_id'])
            answer = question.answer if answer_index < correct_answers else '__definitely_wrong__'
        response = client.post(
            question_path,
            data={
                'csrf_token': csrf_token,
                'question_token': question_token,
                'answer': answer,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        question_path = urlsplit(response.location).path
    return question_path


def test_progression_rules_are_preserved(fundamentals_app):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    start = _start_attempt(client, _session_join_path(fundamentals_app, 'a_pv'), ids['pupil_a'])
    question_path = urlsplit(start.location).path

    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_pv'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (2, None, 1, 1, False)

    question_path = _submit_level(fundamentals_app, client, question_path, 7)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_pv'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (3, 2, 1, 0, False)

    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_pv'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (5, 2, 1, 2, True)
    assert '/fundamentals/pupil/complete/' in question_path


def test_teacher_can_start_place_value_with_recommended_or_overridden_level(fundamentals_app):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    _login(client, ids['teacher_a'])
    with fundamentals_app.app_context():
        pv = FundamentalStrand.query.filter_by(code='PV').one()
        pv_id = pv.id

    start_page = client.get(f"/fundamentals/start?class_id={ids['class_a']}&strand_id={pv_id}")
    assert start_page.status_code == 200
    assert 'Place Value' in start_page.get_data(as_text=True)

    response = client.post('/fundamentals/start', data={
        'csrf_token': _hidden_value(start_page, 'csrf_token'),
        'class_id': ids['class_a'],
        'strand_id': pv_id,
        'start_level': 6,
    }, follow_redirects=False)
    assert response.status_code == 302
    with fundamentals_app.app_context():
        session = (FundamentalSession.query
            .filter_by(class_id=ids['class_a'], strand_id=pv_id, is_active=True)
            .one())
        assert session.start_level == 6
        assert session.academic_year == '2025/26'


def test_place_value_question_sampling_uses_current_level_and_renders_visual(fundamentals_app, monkeypatch):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    client = fundamentals_app.test_client()
    start = _start_attempt(client, _session_join_path(fundamentals_app, 'a_pv'), ids['pupil_a'])
    question_path = urlsplit(start.location).path

    monkeypatch.setattr(
        fundamentals_routes.random,
        'choice',
        lambda questions: next(question for question in questions if question.question_id == 'PV01-01'),
    )
    page = client.get(question_path)
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'A number line runs 0, 1, 2, __, 4.' in body
    assert 'pv-visual-number_line' in body
    assert 'Level 1: Number sequence within 20' in body

    token = _hidden_value(page, 'question_token')
    with fundamentals_app.app_context():
        payload = URLSafeTimedSerializer(
            fundamentals_app.config['SECRET_KEY'],
            signer_kwargs={'digest_method': hashlib.sha256},
        ).loads(token, salt=fundamentals_routes.QUESTION_TOKEN_SALT, max_age=3600)
        question = db.session.get(FundamentalQuestion, payload['question_id'])
        assert question.level_number == 1
        assert question.strand.code == 'PV'


def test_place_value_reporting_and_intervention_skill_are_integrated(fundamentals_app):
    ids = fundamentals_app.config['FUNDAMENTALS_TEST_IDS']
    with fundamentals_app.app_context():
        session = db.session.get(FundamentalSession, ids['a_pv'])
        session.is_active = False
        attempt = FundamentalPupilAttempt(
            session=session,
            pupil_id=ids['pupil_a'],
            current_level=8,
            secure_level=6,
            intervention_level=7,
            below_70_streak=2,
            is_complete=True,
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(attempt)
        db.session.commit()
        pv_id = session.strand_id

    client = fundamentals_app.test_client()
    _login(client, ids['teacher_a'])
    scores = client.get(f"/fundamentals/scores?strand_id={pv_id}")
    levels = client.get(f"/fundamentals/levels?class_id={ids['class_a']}&strand_id={pv_id}")
    interventions = client.get(f"/fundamentals/interventions?class_id={ids['class_a']}&strand_id={pv_id}")

    assert scores.status_code == levels.status_code == interventions.status_code == 200
    assert 'Place Value' in scores.get_data(as_text=True)
    levels_body = levels.get_data(as_text=True)
    assert 'Levels &amp; Questions' in levels_body
    assert 'Cross hundreds boundaries' in levels_body
    intervention_body = interventions.get_data(as_text=True)
    assert 'Place Value' in intervention_body
    assert 'Level 7: Cross hundreds boundaries' in intervention_body
