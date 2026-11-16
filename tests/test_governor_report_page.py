"""The governor report page stays anonymised. Fictional data only."""
from app.extensions import db
from app.models import Pupil, SubjectResult
from test_assessment_reliability import login, world  # noqa: F401


def test_report_has_no_pupil_names_and_loads_for_admin(world):  # noqa: F811
    app, ids = world
    with app.app_context():
        for pupil_id in ids['pupils']:
            db.session.add(SubjectResult(pupil_id=pupil_id, school_id=ids['a'], academic_year='2026/27', term='autumn',
                                         subject='maths', combined_percent=60.0, band_label='On Track'))
        db.session.commit()
    client = app.test_client(); login(client, ids['admin'])
    page = client.get('/admin/reports/governor-summary', query_string={'academic_year': '2026/27'})
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'Alice' not in html and 'Beth' not in html
    assert 'Maths' in html and '&lt;5' in html  # only two pupils are scored, so every group is hidden
    csv_page = client.get('/admin/reports/governor-summary', query_string={'academic_year': '2026/27', 'format': 'csv'})
    assert csv_page.status_code == 200 and b'Alice' not in csv_page.data and b'<5' in csv_page.data


def test_report_is_admin_only(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    assert client.get('/admin/reports/governor-summary').status_code == 403
