"""Pupil timeline on the profile and the one-page progress report. Fictional data only."""
from app.extensions import db
from app.models import AuditLog, Intervention, Pupil, SubjectResult
from test_assessment_reliability import login, world  # noqa: F401


def _results(app, ids):
    with app.app_context():
        for term, percent, band in (('autumn', 50.0, 'Working Towards'), ('spring', 62.0, 'On Track')):
            db.session.add(SubjectResult(pupil_id=ids['pupils'][0], school_id=ids['a'], academic_year='2026/27', term=term,
                                         subject='maths', combined_percent=percent, band_label=band))
        db.session.add(Intervention(school_id=ids['a'], pupil_id=ids['pupils'][0], subject='maths', term='autumn',
                                    academic_year='2026/27', reason='Teacher added', is_active=True))
        pupil = db.session.get(Pupil, ids['pupils'][0])
        pupil.strengths_notes = 'Confident with number bonds'
        pupil.general_notes = 'PRIVATE-STAFF-NOTE'
        db.session.commit()


def test_profile_shows_a_timeline_with_results_and_support(world):  # noqa: F811
    app, ids = world; _results(app, ids)
    client = app.test_client(); login(client, ids['teacher'])
    html = client.get(f'/pupils/{ids["pupils"][0]}').get_data(as_text=True)
    block = html[html.index('id="pupil-timeline"'):]
    assert 'Maths: 62% On Track (+12)' in block and 'Maths: 50% Working Towards' in block
    assert 'Support started: maths' in block or 'Support started: Maths' in block


def test_progress_report_is_a_pdf_and_leaves_out_private_notes(world):  # noqa: F811
    app, ids = world; _results(app, ids)
    client = app.test_client(); login(client, ids['teacher'])
    response = client.get(f'/pupils/{ids["pupils"][0]}/progress-report.pdf')
    assert response.status_code == 200 and response.mimetype == 'application/pdf' and response.data.startswith(b'%PDF')
    assert b'PRIVATE-STAFF-NOTE' not in response.data
    with app.app_context():
        assert AuditLog.query.filter_by(action='pupil_progress_report_downloaded').count() == 1


def test_other_schools_teacher_cannot_get_the_report(world):  # noqa: F811
    app, ids = world; _results(app, ids)
    client = app.test_client(); login(client, ids['other'])
    assert client.get(f'/pupils/{ids["pupils"][0]}/progress-report.pdf').status_code in {403, 404}


def test_report_works_for_a_pupil_with_no_results(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['admin'])
    response = client.get(f'/pupils/{ids["pupils"][1]}/progress-report.pdf')
    assert response.status_code == 200 and response.data.startswith(b'%PDF')
