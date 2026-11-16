"""Term-end scores checklist for leaders. Fictional data only."""
import importlib.util
import pathlib

from app.extensions import db
from app.models import SubjectResult
from test_assessment_reliability import login, world  # noqa: F401


def _score(app, ids, index, subject, term='autumn', percent=55.0, school='a'):
    with app.app_context():
        db.session.add(SubjectResult(pupil_id=ids['pupils'][index], school_id=ids[school], academic_year='2026/27', term=term,
                                     subject=subject, combined_percent=percent, band_label='On Track'))
        db.session.commit()


def _page(app, ids, user='admin', **query):
    client = app.test_client(); login(client, ids[user])
    return client.get('/admin/reports/scores-checklist', query_string={'academic_year': '2026/27', 'term': 'autumn', **query})


def test_status_rules():
    spec = importlib.util.spec_from_file_location('sc', pathlib.Path(__file__).parents[1] / 'app' / 'services' / 'scores_checklist.py')
    # status_for has no imports it needs; load only that function's source to stay database-free
    source = pathlib.Path(spec.origin).read_text()
    namespace = {}
    exec(source[source.index('def status_for'):source.index('def build_checklist')], namespace)
    status = namespace['status_for']
    assert status(0, 0) == 'no_pupils' and status(2, 0) == 'not_started' and status(2, 1) == 'partial' and status(2, 2) == 'complete'


def test_partial_class_names_the_missing_pupil_and_counts(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 'maths')          # Alice has Maths, Beth does not
    html = _page(app, ids).get_data(as_text=True)
    assert 'Beth Test' in html and '1 / 2' in html and '1 missing' in html
    assert 'Not started' in html          # Reading and SPaG have no scores


def test_complete_when_every_pupil_has_a_score(world):  # noqa: F811
    app, ids = world
    for index in (0, 1):
        _score(app, ids, index, 'maths')
    html = _page(app, ids).get_data(as_text=True)
    assert 'Complete' in html and '1 of 3</strong> class and subject checks' in html


def test_other_terms_and_other_schools_do_not_count(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 'maths', term='spring')
    html = _page(app, ids).get_data(as_text=True)
    assert '0 of 3</strong>' in html and 'Complete' not in html.split('<tbody>')[1]
    assert 'Other Pupil' not in html


def test_a_score_without_a_percentage_does_not_count(world):  # noqa: F811
    app, ids = world
    _score(app, ids, 0, 'maths', percent=None)
    assert '0 / 2' in _page(app, ids).get_data(as_text=True)


def test_checklist_is_admin_only_and_rejects_bad_terms(world):  # noqa: F811
    app, ids = world
    assert _page(app, ids, user='teacher').status_code == 403
    assert _page(app, ids, term='christmas').status_code == 400
