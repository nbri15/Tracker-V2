"""Regression tests for the November 2026 security/logic review. All data is synthetic."""
import pytest

from test_assessment_reliability import world, login  # noqa: F401  (pytest fixture)
from app.extensions import db
from app.models import School, SchoolClass, Pupil, SatsResult, User


def _make_executive(app, school_id=None):
    with app.app_context():
        user = User(username='platform-exec', role='executive_admin', is_active=True, school_id=school_id)
        user.set_password('Synthetic exec words here')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.mark.parametrize('exec_has_school', [False, True])
def test_school_admin_cannot_change_executive_account(world, exec_has_school):
    app, ids = world
    exec_id = _make_executive(app, ids['a'] if exec_has_school else None)
    client = app.test_client()
    login(client, ids['admin'])
    response = client.post('/admin/users', data={'action': 'update', 'user_id': exec_id, f'username_{exec_id}': 'renamed'})
    assert response.status_code == 403
    response = client.post('/admin/users', data={'action': 'delete', 'user_id': exec_id})
    assert response.status_code == 403
    with app.app_context():
        executive = db.session.get(User, exec_id)
        assert executive is not None and executive.is_active and executive.username == 'platform-exec'


def test_school_admin_cannot_change_other_school_user(world):
    app, ids = world
    client = app.test_client()
    login(client, ids['admin'])
    response = client.post('/admin/users', data={'action': 'update', 'user_id': ids['other'], f'username_{ids["other"]}': 'renamed'})
    assert response.status_code == 403
    with app.app_context():
        assert db.session.get(User, ids['other']).username == 'teacher-b'


def test_school_admin_can_still_update_own_teacher(world):
    app, ids = world
    client = app.test_client()
    login(client, ids['admin'])
    response = client.post('/admin/users', data={'action': 'update', 'user_id': ids['teacher'], f'username_{ids["teacher"]}': 'teacher-renamed', f'is_active_{ids["teacher"]}': 'on'})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(User, ids['teacher']).username == 'teacher-renamed'


@pytest.fixture
def year6(world):
    """Adds a synthetic Year 6 class (teacher: 'y6-teacher') with one pupil to School A."""
    app, ids = world
    with app.app_context():
        school = db.session.get(School, ids['a'])
        teacher = User(username='y6-teacher', role='teacher', school=school, is_active=True)
        teacher.set_password('password123')
        y6 = SchoolClass(name='Ash', year_group=6, school=school, teacher=teacher, is_active=True)
        db.session.add_all([teacher, y6]); db.session.flush()
        pupil = Pupil(first_name='Synth', last_name='Six', gender='Male', school_class=y6, school_id=school.id, is_active=True)
        db.session.add(pupil); db.session.commit()
        ids = dict(ids, y6_teacher=teacher.id, y6_class=y6.id, y6_pupil=pupil.id)
    return app, ids


def _sats_save(client, pupil_id, field, value, exam_number=1):
    return client.post('/api/sats/simple/quick-save', json={'pupil_id': pupil_id, 'exam_number': exam_number, 'academic_year': '2026/27', 'field': field, 'value': value})


def test_other_year_teacher_cannot_edit_y6_sats(year6):
    app, ids = year6
    client = app.test_client(); login(client, ids['teacher'])  # Year 5 teacher
    assert _sats_save(client, ids['y6_pupil'], 'arithmetic_score', '30').status_code == 403
    assert client.post('/api/sats/simple/add-exam', json={'academic_year': '2026/27'}).status_code == 403
    assert client.post('/api/sats/simple/settings', json={'academic_year': '2026/27', 'exam_number': 1, 'field': 'arithmetic_max', 'value': '5'}).status_code == 403
    with app.app_context():
        assert SatsResult.query.filter_by(pupil_id=ids['y6_pupil']).count() == 0


def test_y6_teacher_and_admin_can_edit_y6_sats(year6):
    app, ids = year6
    for user_id in (ids['y6_teacher'], ids['admin']):
        client = app.test_client(); login(client, user_id)
        response = _sats_save(client, ids['y6_pupil'], 'arithmetic_score', '30')
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['maths_combined_score'] == 30


@pytest.mark.parametrize('field,value', [
    ('arithmetic_score', 'abc'),
    ('arithmetic_score', '-1'),
    ('arithmetic_score', '41'),      # default arithmetic maximum is 40
    ('maths_scaled_score', '79'),
    ('maths_scaled_score', '121'),
    ('reading_score', '3.5'),
])
def test_bad_sats_values_are_rejected_not_crashing(year6, field, value):
    app, ids = year6
    client = app.test_client(); login(client, ids['y6_teacher'])
    client.get('/sats/simple?academic_year=2026/27')  # creates the exam settings rows, as the page does
    response = _sats_save(client, ids['y6_pupil'], field, value)
    assert response.status_code == 400
    assert response.get_json()['error']


@pytest.mark.parametrize('field,value,expected', [('maths_scaled_score', '100', 100), ('arithmetic_score', '40', 40), ('arithmetic_score', '', None)])
def test_good_sats_values_save(year6, field, value, expected):
    app, ids = year6
    client = app.test_client(); login(client, ids['y6_teacher'])
    client.get('/sats/simple?academic_year=2026/27')
    assert _sats_save(client, ids['y6_pupil'], field, value).status_code == 200
    with app.app_context():
        row = SatsResult.query.filter_by(pupil_id=ids['y6_pupil'], exam_number=1).first()
        assert getattr(row, field) == expected


def test_sats_settings_reject_bad_maximum(year6):
    app, ids = year6
    client = app.test_client(); login(client, ids['y6_teacher'])
    response = client.post('/api/sats/simple/settings', json={'academic_year': '2026/27', 'exam_number': 1, 'field': 'arithmetic_max', 'value': 'lots'})
    assert response.status_code == 400


@pytest.mark.parametrize('username', ['%', '_%', 'teacher%', 'TEACHER_A'])
def test_login_username_wildcards_do_not_match(world, username):
    app, ids = world
    client = app.test_client()
    client.post('/auth/login', data={'school_code': 'school-a', 'username': username, 'password': 'password123'})
    with client.session_transaction() as session:
        assert '_user_id' not in session


def test_login_username_is_still_case_insensitive(world):
    app, ids = world
    client = app.test_client()
    response = client.post('/auth/login', data={'school_code': 'school-a', 'username': 'Teacher-A', 'password': 'password123'})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session['_user_id'] == str(ids['teacher'])


def test_seed_script_refuses_non_local_databases():
    from types import SimpleNamespace
    import seed
    for config in (
        {'ENV': 'production', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///x.db'},
        {'ENV': 'development', 'SQLALCHEMY_DATABASE_URI': 'postgresql://example.invalid/db'},
    ):
        with pytest.raises(SystemExit):
            seed.refuse_unless_local_database(SimpleNamespace(config=config))
    seed.refuse_unless_local_database(SimpleNamespace(config={'ENV': 'development', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///dev.db'}))


@pytest.mark.parametrize('environ,allowed', [
    ({'DATABASE_URL': 'postgresql://example.invalid/db'}, False),
    ({'APP_ENV': 'production'}, False),
    ({'APP_ENV': 'development'}, True),
    ({'DATABASE_URL': 'sqlite:///dev.db', 'APP_ENV': 'development'}, True),
])
def test_seed_script_checks_environment_before_connecting(environ, allowed):
    import seed
    if allowed:
        seed.refuse_unless_local_environment(environ)
    else:
        with pytest.raises(SystemExit):
            seed.refuse_unless_local_environment(environ)
