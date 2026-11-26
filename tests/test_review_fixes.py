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


def test_executive_can_create_several_schools_with_their_own_settings(world):
    from app.models import AssessmentSetting, TrackerModeSetting
    from app.services.admin_ops import initialise_school_data
    app, ids = world
    exec_id = _make_executive(app)
    with app.app_context():
        initialise_school_data(ids['a'])  # School A already has the defaults
    client = app.test_client(); login(client, exec_id)
    for name, slug in (('Synthetic C', 'synthetic-c'), ('Synthetic D', 'synthetic-d')):
        response = client.post('/exec/schools', data={'action': 'create', 'name': name, 'slug': slug, 'academic_year': '2026/27', 'is_active': 'on'})
        assert response.status_code == 302
    with app.app_context():
        for slug in ('synthetic-c', 'synthetic-d'):
            school = School.query.filter_by(slug=slug).one()
            assert TrackerModeSetting.query.filter_by(school_id=school.id).count() == 6
            assert TrackerModeSetting.query.filter_by(school_id=school.id, year_group=6).one().tracker_mode == 'sats'
            assert AssessmentSetting.query.filter_by(school_id=school.id).count() == 6 * 3 * 3


def test_failed_school_setup_does_not_leave_half_created_school(world, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    import app.executive.routes as executive_routes
    app, ids = world
    exec_id = _make_executive(app)

    def broken_setup(school_id):
        raise IntegrityError('synthetic failure', None, Exception('synthetic'))

    monkeypatch.setattr(executive_routes, 'initialise_school_data', broken_setup)
    client = app.test_client(); login(client, exec_id)
    client.post('/exec/schools', data={'action': 'create', 'name': 'Synthetic E', 'slug': 'synthetic-e', 'academic_year': '2026/27', 'is_active': 'on'})
    with app.app_context():
        assert School.query.filter_by(slug='synthetic-e').first() is None


def test_per_school_unique_migration_on_sqlite():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / 'migrations/versions/20261126_01_per_school_unique_settings.py'
    spec = importlib.util.spec_from_file_location('per_school_unique_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE tracker_mode_settings (id INTEGER PRIMARY KEY, school_id INTEGER, year_group INTEGER NOT NULL, tracker_mode VARCHAR(20), CONSTRAINT uq_tracker_mode_year_group UNIQUE (year_group))'))
        connection.execute(sa.text('CREATE TABLE phonics_test_columns (id INTEGER PRIMARY KEY, school_id INTEGER, year_group INTEGER NOT NULL, name VARCHAR(120) NOT NULL, CONSTRAINT uq_phonics_test_column_name UNIQUE (year_group, name))'))
        connection.execute(sa.text("INSERT INTO tracker_mode_settings (school_id, year_group, tracker_mode) VALUES (1, 6, 'sats')"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        connection.execute(sa.text("INSERT INTO tracker_mode_settings (school_id, year_group, tracker_mode) VALUES (2, 6, 'sats')"))
        connection.execute(sa.text("INSERT INTO phonics_test_columns (school_id, year_group, name) VALUES (1, 1, 'Check'), (2, 1, 'Check')"))
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("INSERT INTO tracker_mode_settings (school_id, year_group, tracker_mode) VALUES (2, 6, 'normal')"))
        assert connection.execute(sa.text('SELECT COUNT(*) FROM tracker_mode_settings')).scalar() == 2


def _year_ids(app):
    from app.models import AcademicYear
    with app.app_context():
        return {year.name: year.id for year in AcademicYear.query.all()}


def test_viewing_a_past_year_shows_a_banner(world):
    app, ids = world
    years = _year_ids(app)
    client = app.test_client(); login(client, ids['teacher'])
    page = client.get(f'/teacher/maths?year={years["2025/26"]}')
    assert page.status_code == 200
    assert b'data-testid="viewing-year-notice"' in page.data
    assert b'You are looking at 2025/26' in page.data
    # The choice is remembered on the next page...
    assert b'You are looking at 2025/26' in client.get('/teacher/maths').data
    # ...and the banner button takes them back to the current year.
    client.post('/set-academic-year', data={'academic_year_id': years['2026/27']}, headers={'Referer': 'http://localhost/teacher/maths'})
    assert b'data-testid="viewing-year-notice"' not in client.get('/teacher/maths').data


def test_current_year_has_no_banner(world):
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    assert b'data-testid="viewing-year-notice"' not in client.get('/teacher/maths').data


def test_rollover_resets_a_remembered_year(world):
    from app.models import AcademicYear
    app, ids = world
    years = _year_ids(app)
    client = app.test_client(); login(client, ids['teacher'])
    client.get(f'/teacher/maths?year={years["2026/27"]}')  # teacher is working in 2026/27
    with app.app_context():  # meanwhile the admin rolls the school over
        new_year = AcademicYear(name='2027/28'); db.session.add(new_year); db.session.flush()
        db.session.get(School, ids['a']).current_academic_year = new_year
        db.session.commit()
    page = client.get('/teacher/maths')
    assert b'data-testid="viewing-year-notice"' not in page.data
    with client.session_transaction() as session:
        assert session['selected_academic_year_id'] == new_year_id(app)


def new_year_id(app):
    from app.models import AcademicYear
    with app.app_context():
        return AcademicYear.query.filter_by(name='2027/28').one().id


def test_year_switch_returns_to_same_page(world):
    app, ids = world
    years = _year_ids(app)
    client = app.test_client(); login(client, ids['teacher'])
    response = client.post('/set-academic-year', data={'academic_year_id': years['2025/26']}, headers={'Referer': 'http://localhost/teacher/maths?term=spring'})
    assert response.headers['Location'].endswith('/teacher/maths?term=spring')
    response = client.post('/set-academic-year', data={'academic_year_id': years['2025/26']}, headers={'Referer': 'https://evil.example/phish'})
    assert response.headers['Location'].endswith('/dashboard')


def _sign_in(app, school_code, username, password):
    client = app.test_client()
    response = client.post('/auth/login', data={'school_code': school_code, 'username': username, 'password': password})
    assert response.status_code == 302
    return client


def test_password_reset_signs_out_other_devices(world):
    app, ids = world
    teacher_ipad = _sign_in(app, 'school-a', 'teacher-a', 'password123')
    assert teacher_ipad.get('/dashboard/teacher').status_code == 200
    admin = _sign_in(app, 'school-a', 'admin-a', 'password123')
    response = admin.post(f'/admin/users/{ids["teacher"]}/reset-password', data={'new_password': 'Purple tractor biscuit', 'confirm_password': 'Purple tractor biscuit'})
    assert response.status_code == 302
    response = teacher_ipad.get('/dashboard/teacher')
    assert response.status_code == 302 and '/auth/login' in response.headers['Location']
    # The admin who did the reset stays signed in.
    assert admin.get('/admin/users').status_code == 200


def test_changing_own_password_keeps_this_device_signed_in(world):
    app, ids = world
    device_one = _sign_in(app, 'school-a', 'teacher-a', 'password123')
    device_two = _sign_in(app, 'school-a', 'teacher-a', 'password123')
    response = device_one.post('/auth/change-password', data={'new_password': 'Orange kettle meadow', 'confirm_password': 'Orange kettle meadow'})
    assert response.status_code == 302
    assert device_one.get('/dashboard/teacher').status_code == 200
    assert device_two.get('/dashboard/teacher').status_code == 302


def test_executive_school_admin_creation_uses_password_rules(world):
    app, ids = world
    exec_id = _make_executive(app)
    client = app.test_client(); login(client, exec_id)
    client.post(f'/exec/schools/{ids["b"]}/create-admin', data={'username': 'weak-admin', 'password': 'short1'})
    client.post(f'/exec/schools/{ids["b"]}/users/{ids["other"]}/reset-password', data={'new_password': 'password1234'})
    with app.app_context():
        assert User.query.filter_by(username='weak-admin').first() is None
        assert db.session.get(User, ids['other']).check_password('password123')


@pytest.mark.parametrize('value,expected', [
    ('=HYPERLINK("http://example.invalid")', '\'=HYPERLINK("http://example.invalid")'),
    ('+44 call', "'+44 call"),
    ('@SUM(A1)', "'@SUM(A1)"),
    ('-5', '-5'),
    ('-', "'-"),
    ('Alice', 'Alice'),
    (12, 12),
    (None, None),
])
def test_safe_csv_cell(value, expected):
    from app.services.safe_csv import safe_cell
    assert safe_cell(value) == expected


def test_csv_and_xlsx_exports_neutralise_formulas():
    import io
    from openpyxl import Workbook, load_workbook
    from app.services import safe_csv
    out = io.StringIO()
    safe_csv.writer(out).writerow(['=1+1', 'ok', -3])
    assert out.getvalue().strip() == "'=1+1,ok,-3"
    out = io.StringIO()
    writer = safe_csv.DictWriter(out, fieldnames=['a'])
    writer.writeheader(); writer.writerow({'a': '=cmd'})
    assert out.getvalue().splitlines()[1] == "'=cmd"
    wb = Workbook(); wb.active.append(['=1+1', 'plain'])
    safe_csv.neutralise_workbook_formulas(wb)
    data = io.BytesIO(); wb.save(data); data.seek(0)
    cell = load_workbook(data).active['A1']
    assert cell.value == '=1+1' and cell.data_type == 's'


def test_rollover_works_when_an_archived_class_has_the_default_name(world):
    from app.services.admin_ops import promote_pupils_to_next_year
    app, ids = world
    with app.app_context():
        school = db.session.get(School, ids['a'])
        db.session.add(SchoolClass(name='Year 6', year_group=6, school=school, is_active=False))  # archived years ago
        db.session.commit()
        outcome = promote_pupils_to_next_year('2026/27', ids['a'], class_mapping={ids['ca']: None})
        db.session.commit()
        assert outcome['moved'] == 2
        new_class = SchoolClass.query.filter_by(school_id=ids['a'], year_group=6, is_active=True).one()
        assert new_class.name == 'Year 6 (2027/28)'
        assert {pupil.class_id for pupil in Pupil.query.filter(Pupil.id.in_(ids['pupils']))} == {new_class.id}


def test_go_back_button_works_when_the_address_contains_a_year(world):
    app, ids = world
    years = _year_ids(app)
    client = app.test_client(); login(client, ids['teacher'])
    client.get(f'/teacher/maths?year={years["2025/26"]}&term=spring')
    response = client.post('/set-academic-year', data={'academic_year_id': years['2026/27']},
                           headers={'Referer': f'http://localhost/teacher/maths?year={years["2025/26"]}&term=spring'})
    assert response.headers['Location'].endswith('/teacher/maths?term=spring')
    assert b'data-testid="viewing-year-notice"' not in client.get(response.headers['Location']).data


def test_sats_page_shows_blank_not_none_for_empty_cells(year6):
    app, ids = year6
    client = app.test_client(); login(client, ids['y6_teacher'])
    client.get('/sats/simple?academic_year=2026/27')
    assert _sats_save(client, ids['y6_pupil'], 'arithmetic_score', '30').status_code == 200
    page = client.get(f'/sats/simple?academic_year=2026/27&class_id={ids["y6_class"]}')
    assert b'value="30"' in page.data
    assert b'value="None"' not in page.data
