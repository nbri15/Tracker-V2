import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Flask
import sqlalchemy as sa

from app.auth import auth_bp
from app.auth.routes import _login_rollover_years
from app.extensions import db, login_manager
from app.models import AcademicYear, School, User
from app.services import get_selected_academic_year, get_selected_current_academic_year


def _app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY='test',
        SQLALCHEMY_DATABASE_URI='sqlite://',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def _load_repair_migration():
    migration_path = Path(__file__).parents[1] / 'migrations' / 'versions' / '20260901_01_rewind_unpromoted_working_year.py'
    spec = importlib.util.spec_from_file_location('working_year_repair', migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_all_schools_repair_migration():
    migration_path = Path(__file__).parents[1] / 'migrations' / 'versions' / '20260903_01_rewind_all_working_years.py'
    spec = importlib.util.spec_from_file_location('all_schools_working_year_repair', migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_rewinds_only_schools_without_recorded_promotion():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    years = sa.Table(
        'academic_years', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(20), unique=True, nullable=False),
        sa.Column('is_current', sa.Boolean, nullable=False),
        sa.Column('is_archived', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    schools = sa.Table(
        'schools', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('current_academic_year_id', sa.Integer),
    )
    history = sa.Table(
        'pupil_class_history', metadata,
        sa.Column('school_id', sa.Integer),
        sa.Column('academic_year', sa.String(20)),
        sa.Column('promoted_to_year_group', sa.Integer),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        connection.execute(years.insert(), [
            {'id': 1, 'name': '2025/26', 'is_current': False, 'is_archived': False, 'created_at': created_at},
            {'id': 2, 'name': '2026/27', 'is_current': True, 'is_archived': False, 'created_at': created_at},
        ])
        connection.execute(schools.insert(), [
            {'id': 10, 'current_academic_year_id': 2},
            {'id': 20, 'current_academic_year_id': 2},
        ])
        connection.execute(history.insert(), [
            {'school_id': 20, 'academic_year': '2025/26', 'promoted_to_year_group': 3},
            {'school_id': None, 'academic_year': '2025/26', 'promoted_to_year_group': 4},
        ])

        repaired = _load_repair_migration().rewind_unpromoted_schools(connection)
        selected = dict(connection.execute(sa.select(schools.c.id, schools.c.current_academic_year_id)).all())

    assert repaired == 1
    assert selected == {10: 1, 20: 2}


def test_explicit_repair_rewinds_every_school_on_unconfirmed_year():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    years = sa.Table(
        'academic_years', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(20), unique=True, nullable=False),
    )
    schools = sa.Table(
        'schools', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('slug', sa.String(140), unique=True, nullable=False),
        sa.Column('current_academic_year_id', sa.Integer),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(years.insert(), [
            {'id': 1, 'name': '2025/26'},
            {'id': 2, 'name': '2026/27'},
        ])
        connection.execute(schools.insert(), [
            {'id': 10, 'slug': 'barrow-school', 'current_academic_year_id': 2},
            {'id': 20, 'slug': 'another-school', 'current_academic_year_id': 2},
            {'id': 30, 'slug': 'already-old-year', 'current_academic_year_id': 1},
        ])

        repaired = _load_all_schools_repair_migration().rewind_all_schools(connection)
        selected = dict(connection.execute(sa.select(schools.c.id, schools.c.current_academic_year_id)).all())

    assert repaired == 2
    assert selected == {10: 1, 20: 1, 30: 1}


def test_school_admin_login_redirects_to_rollover_review(monkeypatch):
    app = _app()
    app.config['WTF_CSRF_ENABLED'] = False
    login_manager.init_app(app)

    dashboards = Blueprint('dashboards', __name__)
    admin_routes = Blueprint('admin', __name__)

    @dashboards.get('/dashboard')
    def index():
        return 'dashboard'

    @admin_routes.get('/admin/promotion')
    def promotion():
        return 'promotion'

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboards)
    app.register_blueprint(admin_routes)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        old_year = AcademicYear(name='2025/26')
        school = School(name='School', slug='school', current_academic_year=old_year)
        admin = User(username='admin', role='school_admin', school=school, is_active=True)
        teacher = User(username='teacher', role='teacher', school=school, is_active=True)
        admin.set_password('password123')
        teacher.set_password('password123')
        db.session.add_all([old_year, school, admin, teacher])
        db.session.commit()

        monkeypatch.setattr('app.auth.routes.get_current_academic_year', lambda: '2026/27')
        assert _login_rollover_years(admin) == ('2025/26', '2026/27')
        assert _login_rollover_years(teacher) is None

    response = app.test_client().post('/auth/login', data={
        'school_code': 'school',
        'username': 'admin',
        'password': 'password123',
    })
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/promotion?rollover_prompt=1')

    with app.test_client() as client:
        with client.session_transaction() as session:
            session['_user_id'] = str(admin.id)
            session['_fresh'] = True
        response = client.get('/dashboard')
        assert response.status_code == 200
        with app.test_request_context('/tracker'):
            from flask_login import login_user

            login_user(admin)
            assert get_selected_current_academic_year() == '2025/26'
            assert get_selected_academic_year().name == '2025/26'
