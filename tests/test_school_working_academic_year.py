from flask import Flask, session

from app.extensions import db
from app.models import AcademicYear, School
from app.services import get_school_working_academic_year, is_academic_year_rollover_due, promote_pupils_to_next_year


def test_rollover_prompt_only_appears_after_calendar_advances():
    assert is_academic_year_rollover_due('2025/26', '2026/27') is True
    assert is_academic_year_rollover_due('2025/26', '2025/26') is False
    assert is_academic_year_rollover_due('2026/27', '2025/26') is False


def _app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY='test',
        SQLALCHEMY_DATABASE_URI='sqlite://',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def test_working_year_is_school_scoped_and_ignores_viewing_session():
    app = _app()
    with app.app_context():
        db.create_all()
        years = [AcademicYear(name=name, is_current=name == '2027/28') for name in ('2024/25', '2025/26', '2026/27', '2027/28')]
        db.session.add_all(years)
        db.session.flush()
        school_a = School(name='School A', slug='school-a', current_academic_year=years[1])
        school_b = School(name='School B', slug='school-b', current_academic_year=years[2])
        db.session.add_all([school_a, school_b])
        db.session.commit()

        with app.test_request_context('/'):
            session['selected_academic_year_id'] = years[0].id
            assert get_school_working_academic_year(school_a.id).name == '2025/26'
            session['selected_academic_year_id'] = years[2].id
            assert get_school_working_academic_year(school_a.id).name == '2025/26'
            assert get_school_working_academic_year(school_b.id).name == '2026/27'


def test_promotion_advances_only_the_selected_schools_working_year():
    app = _app()
    with app.app_context():
        db.create_all()
        year_a = AcademicYear(name='2025/26', is_current=True)
        year_b = AcademicYear(name='2026/27')
        school_a = School(name='School A', slug='school-a', current_academic_year=year_a)
        school_b = School(name='School B', slug='school-b', current_academic_year=year_b)
        db.session.add_all([year_a, year_b, school_a, school_b])
        db.session.commit()

        outcome = promote_pupils_to_next_year('2025/26', school_a.id)
        db.session.commit()

        assert outcome['target_year'] == '2026/27'
        assert school_a.current_academic_year.name == '2026/27'
        assert school_b.current_academic_year.name == '2026/27'
        assert AcademicYear.query.filter_by(name='2025/26').one().is_current is True

        try:
            promote_pupils_to_next_year('2025/26', school_a.id)
        except ValueError as exc:
            assert 'already working in 2026/27' in str(exc)
        else:
            raise AssertionError('A second promotion from the old working year should be rejected.')
