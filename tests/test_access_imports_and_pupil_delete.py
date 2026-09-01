from flask import Flask
from flask_login import login_user
from werkzeug.exceptions import Forbidden

from app.admin.routes import _delete_pupil_linked_data
from app.extensions import db, login_manager
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
from app.services.csv_tools import import_combined_results
from app.utils import school_scoped_query, teacher_required


def _app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    return app


def _user(school: School, username: str, role: str = 'teacher') -> User:
    user = User(username=username, role=role, school_id=school.id, is_active=True)
    user.set_password('password123')
    db.session.add(user)
    db.session.flush()
    return user


def test_school_scoped_queries_and_combined_import_do_not_cross_tenants():
    app = _app()
    with app.app_context():
        db.create_all()
        school_a = School(name='School A', slug='school-a')
        school_b = School(name='School B', slug='school-b')
        db.session.add_all([school_a, school_b]); db.session.flush()
        teacher_a = _user(school_a, 'teacher-a')
        class_b = SchoolClass(name='Year 5', year_group=5, school_id=school_b.id)
        db.session.add(class_b); db.session.commit()

        with app.test_request_context('/'):
            login_user(teacher_a)
            assert school_scoped_query(SchoolClass, SchoolClass.query).count() == 0
            summary = import_combined_results([{
                'pupil': 'Alice Test', 'class_name': 'Year 5', 'year_group': '5',
                'academic_year': '2025/26', 'gender': 'female',
            }])
            db.session.commit()
            assert summary.pupils_created == 1
            assert SchoolClass.query.filter_by(school_id=school_a.id, name='Year 5').count() == 1
            assert Pupil.query.filter_by(school_id=school_a.id, first_name='Alice').count() == 1
            assert Pupil.query.filter_by(school_id=school_b.id).count() == 0


def test_teacher_permission_rejects_school_admin():
    app = _app()

    @app.get('/teacher-only')
    @teacher_required
    def teacher_only():
        return 'ok'

    with app.app_context():
        db.create_all()
        school = School(name='School', slug='school')
        db.session.add(school); db.session.flush()
        teacher = _user(school, 'teacher')
        admin = _user(school, 'admin', role='school_admin')
        db.session.commit()

        with app.test_request_context('/teacher-only'):
            login_user(teacher)
            assert teacher_only() == 'ok'
        with app.test_request_context('/teacher-only'):
            login_user(admin)
            try:
                teacher_only()
            except Forbidden:
                pass
            else:
                raise AssertionError('A school admin was allowed through a teacher-only permission check.')


def test_pupil_delete_removes_maths_fundamentals_attempts_first():
    app = _app()
    with app.app_context():
        db.create_all()
        school = School(name='School', slug='school')
        db.session.add(school); db.session.flush()
        teacher = _user(school, 'teacher')
        school_class = SchoolClass(name='Year 5', year_group=5, school_id=school.id, teacher_id=teacher.id)
        db.session.add(school_class); db.session.flush()
        pupil = Pupil(school_id=school.id, first_name='Delete', last_name='Me', gender='female', class_id=school_class.id, is_archived=True)
        strand = FundamentalStrand(code='delete-test', name='Delete test')
        question = FundamentalQuestion(strand=strand, level_number=1, question_id='q1', question_text='1 + 1', answer='2')
        session = FundamentalSession(school_class=school_class, teacher=teacher, strand=strand, start_level=1)
        attempt = FundamentalPupilAttempt(session=session, pupil=pupil, current_level=1)
        response = FundamentalResponse(attempt=attempt, question=question, level_number=1, pupil_answer='2', is_correct=True)
        db.session.add_all([pupil, strand, question, session, attempt, response]); db.session.commit()

        _delete_pupil_linked_data(pupil)
        db.session.delete(pupil)
        db.session.commit()

        assert FundamentalPupilAttempt.query.count() == 0
        assert FundamentalResponse.query.count() == 0
        assert Pupil.query.count() == 0
