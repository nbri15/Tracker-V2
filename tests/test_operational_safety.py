from flask import Flask

from app.extensions import db
from app.executive.routes import _permanently_delete_school_data, _validate_school_payload
from app.models import (
    AuditLog,
    FundamentalPupilAttempt,
    FundamentalQuestion,
    FundamentalResponse,
    FundamentalSession,
    FundamentalStrand,
    Pupil,
    School,
    SchoolClass,
    SimpleSatsExamTab,
    SimpleSatsSetting,
    User,
)


def _app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    return app


def test_school_payload_rejects_blank_invalid_and_duplicate_values():
    app = _app()
    with app.app_context():
        db.create_all()
        db.session.add(School(name='Existing School', slug='existing-school'))
        db.session.commit()

        for name, slug in [('', 'new-school'), ('New School', ''), ('New School', 'Bad Code!'), ('Existing School', 'different')]:
            try:
                _validate_school_payload(name, slug)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Invalid school payload was accepted: {name!r}, {slug!r}')


def test_permanent_school_delete_removes_fundamentals_and_simple_sats_links():
    app = _app()
    with app.app_context():
        db.create_all()
        school = School(name='Delete Me', slug='delete-me', is_archived=True, is_active=False)
        db.session.add(school)
        db.session.flush()
        teacher = User(username='teacher', role='teacher', school_id=school.id)
        teacher.set_password('password123')
        db.session.add(teacher)
        db.session.flush()
        school_class = SchoolClass(name='Year 5', year_group=5, school_id=school.id, teacher_id=teacher.id)
        db.session.add(school_class)
        db.session.flush()
        pupil = Pupil(school_id=school.id, first_name='Test', last_name='Pupil', gender='female', class_id=school_class.id)
        db.session.add(pupil)
        db.session.flush()
        strand = FundamentalStrand(code='test', name='Test strand')
        question = FundamentalQuestion(strand=strand, level_number=1, question_id='q1', question_text='1 + 1', answer='2')
        session = FundamentalSession(school_class=school_class, teacher=teacher, strand=strand, start_level=1)
        attempt = FundamentalPupilAttempt(session=session, pupil=pupil, current_level=1)
        response = FundamentalResponse(attempt=attempt, question=question, level_number=1, pupil_answer='2', is_correct=True)
        db.session.add_all([
            strand, question, session, attempt, response,
            SimpleSatsExamTab(school_id=school.id, academic_year='2025/26', exam_number=1, name='Exam 1'),
            SimpleSatsSetting(school_id=school.id, academic_year='2025/26', exam_number=1),
        ])
        db.session.commit()

        _permanently_delete_school_data(school)
        db.session.delete(school)
        db.session.commit()

        assert FundamentalSession.query.count() == 0
        assert FundamentalPupilAttempt.query.count() == 0
        assert FundamentalResponse.query.count() == 0
        assert SimpleSatsExamTab.query.count() == 0
        assert SimpleSatsSetting.query.count() == 0
        assert School.query.count() == 0
