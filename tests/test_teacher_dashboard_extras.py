"""Teacher dashboard 'needs attention' and support progress. Fictional data only."""
from app.extensions import db
from app.models import Intervention, SubjectResult
from test_assessment_reliability import login, world  # noqa: F401


def _score(app, ids, pupil_index, percent, band, subject='maths', term='autumn'):
    with app.app_context():
        db.session.add(SubjectResult(pupil_id=ids['pupils'][pupil_index], school_id=ids['a'], academic_year='2026/27',
                                     term=term, subject=subject, combined_percent=percent, band_label=band))
        db.session.commit()


def _page(app, ids):
    client = app.test_client(); login(client, ids['teacher'])
    response = client.get('/dashboard/teacher')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_below_pass_pupil_without_support_is_listed_and_unscored_pupil_is_missing(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 30.0, 'Working Towards')
    html = _page(app, ids)
    block = html[html.index('id="needs-attention"'):]
    assert 'Alice Test' in block and 'below the pass mark with no support yet' in block
    assert '1</strong> of 2 pupils have no score this term' in block


def test_pupil_with_active_support_is_not_listed_as_needing_it(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 30.0, 'Working Towards')
    with app.app_context():
        db.session.add(Intervention(school_id=ids['a'], pupil_id=ids['pupils'][0], subject='maths', term='autumn',
                                    academic_year='2026/27', reason='Teacher added', is_active=True))
        db.session.commit()
    html = _page(app, ids)
    block = html[html.index('id="needs-attention"'):html.index('id="support-progress"')]
    assert 'Alice Test' not in block
    assert 'id="support-progress"' in html


def test_on_track_pupils_are_not_flagged_and_other_schools_never_appear(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 80.0, 'On Track')
    html = _page(app, ids)
    block = html[html.index('id="needs-attention"'):]
    assert 'Alice Test' not in block and 'Other Pupil' not in html


def test_dashboard_still_loads_with_no_scores_at_all(world):  # noqa: F811
    app, ids = world
    html = _page(app, ids)
    assert 'No scores yet' in html
