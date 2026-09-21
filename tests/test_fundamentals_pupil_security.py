import html
import hashlib
import re
from urllib.parse import urlsplit

import pytest
from itsdangerous import URLSafeTimedSerializer

from app import create_app
from app.extensions import db
from app.fundamentals import routes as fundamentals_routes
from app.fundamentals.seed import seed_fundamentals
from app.models import (
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
        school_a = School(name='School A', slug='school-a')
        school_b = School(name='School B', slug='school-b')
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
        sessions = {
            'a_ens': FundamentalSession(class_id=class_a.id, teacher_id=teacher_a.id, strand_id=ens.id, start_level=1),
            'a_nb': FundamentalSession(class_id=class_a.id, teacher_id=teacher_a.id, strand_id=nb.id, start_level=1),
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
    start = _start_attempt(client, _session_join_path(fundamentals_app, 'a_ens'), ids['pupil_a'])
    question_path = urlsplit(start.location).path

    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_ens'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (2, None, 1, 1, False)

    question_path = _submit_level(fundamentals_app, client, question_path, 7)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_ens'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (3, 2, 1, 0, False)

    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    question_path = _submit_level(fundamentals_app, client, question_path, 6)
    with fundamentals_app.app_context():
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=ids['a_ens'], pupil_id=ids['pupil_a']).one()
        assert (attempt.current_level, attempt.secure_level, attempt.intervention_level, attempt.below_70_streak, attempt.is_complete) == (5, 2, 1, 2, True)
    assert '/fundamentals/pupil/complete/' in question_path
