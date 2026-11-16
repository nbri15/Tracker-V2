"""Baselines, end dates and impact figures wired into the pages. Fictional, disposable data."""
import csv
import io

from flask_login import login_user

from app.extensions import db
from app.models import Intervention, Pupil, SchoolClass, SubjectResult, User
from app.services.assessment_reliability import apply_result
from app.services.assessments import get_subject_setting
from app.services.intervention_impact import outcomes_for
from app.services.interventions import sync_auto_interventions
from test_assessment_reliability import login
from test_assessment_reliability import world  # noqa: F401  (fixture needed by library)
from test_intervention_programmes import SCOPE, library  # noqa: F401  (pytest fixtures)


def _save_low_autumn_result(app, ids, pupil_id):
    """Save a fictional low autumn Maths score and let the app flag the pupil automatically."""
    with app.app_context(), app.test_request_context('/'):
        login_user(db.session.get(User, ids['teacher']))
        pupil = db.session.get(Pupil, pupil_id)
        setting = get_subject_setting(5, 'maths', 'autumn', '2026/27')
        result = SubjectResult(pupil=pupil, school_id=ids['a'], **SCOPE)
        db.session.add(result)
        apply_result(result, setting, 10, 10)
        db.session.flush()
        percent = result.combined_percent
        sync_auto_interventions(db.session.get(SchoolClass, ids['ca']), 'maths', 'autumn', '2026/27', 55)
        db.session.commit()
        return percent


def test_auto_flagged_pupil_gets_a_baseline_and_start_date(library):  # noqa: F811
    app, ids = library
    percent = _save_low_autumn_result(app, ids, ids['pupils'][1])
    with app.app_context():
        record = Intervention.query.filter_by(pupil_id=ids['pupils'][1], subject='maths', term='autumn').one()
        assert record.baseline_percent == percent and record.started_on is not None


def test_baseline_is_not_rewritten_when_scores_are_saved_again(library):  # noqa: F811
    app, ids = library
    _save_low_autumn_result(app, ids, ids['pupils'][1])
    with app.app_context():
        record = Intervention.query.filter_by(pupil_id=ids['pupils'][1], subject='maths', term='autumn').one()
        record.baseline_percent = 33.0
        db.session.commit()
    with app.app_context(), app.test_request_context('/'):
        login_user(db.session.get(User, ids['teacher']))
        # Saving scores again re-runs the automatic flagging; the starting score must stay.
        sync_auto_interventions(db.session.get(SchoolClass, ids['ca']), 'maths', 'autumn', '2026/27', 55)
        db.session.commit()
    with app.app_context():
        record = Intervention.query.filter_by(pupil_id=ids['pupils'][1], subject='maths', term='autumn').one()
        assert record.baseline_percent == 33.0


def test_old_record_without_baseline_is_estimated_and_never_zero(library):  # noqa: F811
    app, ids = library
    with app.app_context():
        record = db.session.get(Intervention, ids['record'])
        assert outcomes_for([record])[record.id]['status'] == 'no_baseline'
        db.session.add(SubjectResult(pupil_id=record.pupil_id, school_id=ids['a'], **SCOPE, combined_percent=45))
        db.session.flush()
        outcome = outcomes_for([record])[record.id]
        assert outcome['baseline_percent'] == 45.0 and outcome['baseline_source'] == 'estimated'
        assert outcome['status'] == 'awaiting'


def test_next_assessment_gives_the_change_and_pass_level(library):  # noqa: F811
    app, ids = library
    with app.app_context():
        record = db.session.get(Intervention, ids['record'])
        record.baseline_percent = 40.0
        db.session.add(SubjectResult(
            pupil_id=record.pupil_id, school_id=ids['a'], subject='maths', term='spring', academic_year='2026/27',
            combined_percent=55, configuration_snapshot={'below_are_threshold_percent': 50}))
        db.session.flush()
        outcome = outcomes_for([record])[record.id]
        assert outcome['baseline_source'] == 'recorded' and outcome['follow_term'] == 'spring'
        assert outcome['change'] == 15.0 and outcome['status'] == 'improved' and outcome['met_threshold'] is True


def test_closing_sets_an_end_date_and_reopening_clears_it(library):  # noqa: F811
    app, ids = library
    client = app.test_client()
    login(client, ids['teacher'])
    client.post('/teacher/interventions', data={**SCOPE, 'action': 'close', 'record_id': ids['record']})
    with app.app_context():
        assert db.session.get(Intervention, ids['record']).ended_on is not None
    client.post('/teacher/interventions', data={**SCOPE, 'action': 'reopen', 'record_id': ids['record']})
    with app.app_context():
        assert db.session.get(Intervention, ids['record']).ended_on is None


def test_pages_and_export_show_impact(library):  # noqa: F811
    app, ids = library
    client = app.test_client()
    login(client, ids['teacher'])
    page = client.get('/teacher/interventions', query_string=SCOPE)
    assert page.status_code == 200 and b'Progress since support began' in page.data
    login(client, ids['admin'])
    page = client.get('/admin/interventions', query_string={'academic_year': '2026/27'})
    assert page.status_code == 200 and b'<th>Impact</th>' in page.data
    response = client.get('/admin/exports/interventions', query_string={'academic_year': '2026/27', 'status': 'all'})
    assert response.status_code == 200
    columns = csv.DictReader(io.StringIO(response.data.decode())).fieldnames
    assert {'programmes', 'started_on', 'baseline_percent', 'follow_up_percent', 'change_points', 'impact_status'} <= set(columns)
