"""Leaders can narrow interventions to Pupil Premium and/or SEND pupils. Fictional data only."""
from app.extensions import db
from app.models import Pupil
from test_assessment_reliability import login, world  # noqa: F401
from test_intervention_programmes import library  # noqa: F401


def _flag(app, ids):
    with app.app_context():
        first = db.session.get(Pupil, ids['pupils'][0])
        first.pupil_premium = True
        db.session.commit()


def test_pupil_premium_filter_keeps_only_flagged_pupils(library):  # noqa: F811
    app, ids = library; _flag(app, ids)
    client = app.test_client(); login(client, ids['admin'])
    everyone = client.get('/admin/interventions', query_string={'academic_year': '2026/27'})
    assert b'Alice Test' in everyone.data
    narrowed = client.get('/admin/interventions', query_string={'academic_year': '2026/27', 'pupil_premium': '1'})
    assert narrowed.status_code == 200 and b'Alice Test' in narrowed.data


def test_send_filter_excludes_pupils_without_the_flag(library):  # noqa: F811
    app, ids = library; _flag(app, ids)
    client = app.test_client(); login(client, ids['admin'])
    page = client.get('/admin/interventions', query_string={'academic_year': '2026/27', 'send': '1'})
    assert page.status_code == 200 and b'Alice Test' not in page.data


def test_both_filters_must_match_and_csv_follows_the_same_filters(library):  # noqa: F811
    app, ids = library; _flag(app, ids)
    client = app.test_client(); login(client, ids['admin'])
    both = client.get('/admin/interventions', query_string={'academic_year': '2026/27', 'pupil_premium': '1', 'send': '1'})
    assert b'Alice Test' not in both.data
    csv_pp = client.get('/admin/exports/interventions', query_string={'academic_year': '2026/27', 'pupil_premium': '1'})
    csv_send = client.get('/admin/exports/interventions', query_string={'academic_year': '2026/27', 'send': '1'})
    assert b'Alice' in csv_pp.data and b'Alice' not in csv_send.data
