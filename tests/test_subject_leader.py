"""Subject leader view, scores-entry strip and sidebar links. Fictional data only."""
from app.extensions import db
from app.models import SubjectResult
from app.services.subject_leader import build_subject_view
from test_assessment_reliability import login, world  # noqa: F401


def _summary(wt=0, ot=0, ex=0, avg=None, label='Autumn'):
    scored = wt + ot + ex
    return {'working_towards': wt, 'on_track': ot, 'exceeding': ex, 'average_percent': avg,
            'term_label': label if scored else 'No data'}


def _row(name, year, pupils, **summary):
    return {'class_id': hash(name) % 1000, 'class_name': name, 'year_group': year, 'teacher_name': 'T',
            'pupil_count': pupils, 'active_interventions': 1, 'subjects': {'maths': _summary(**summary)}}


# ---- pure logic ---------------------------------------------------------------------------

def test_year_group_and_whole_school_totals_add_up():
    view = build_subject_view([_row('5A', 5, 10, wt=2, ot=6, ex=2), _row('5B', 5, 10, wt=5, ot=4, ex=1),
                               _row('6A', 6, 10, wt=1, ot=8, ex=1)], 'maths')
    year5 = next(g for g in view['year_groups'] if g['year_group'] == 5)
    assert year5['classes'] == 2 and year5['scored'] == 20 and year5['on_track_plus'] == 13
    assert year5['on_track_plus_percent'] == 65.0
    school = view['whole_school']
    assert school['scored'] == 30 and school['on_track_plus'] == 22 and school['pupil_count'] == 30
    assert school['active_interventions'] == 3


def test_missing_counts_pupils_without_a_result_and_rows_are_in_year_order():
    view = build_subject_view([_row('6A', 6, 10, ot=4), _row('5A', 5, 10, ot=10)], 'maths')
    assert [r['class_name'] for r in view['rows']] == ['5A', '6A']
    assert view['rows'][1]['missing'] == 6 and view['rows'][0]['missing'] == 0


def test_empty_classes_do_not_divide_by_zero_or_win_the_comparison():
    view = build_subject_view([_row('5A', 5, 10, ot=8, wt=2), _row('5B', 5, 10)], 'maths')
    assert view['rows'][1]['on_track_plus_percent'] == 0.0 and view['rows'][1]['scored'] == 0
    assert view['highest'] is None and view['lowest'] is None  # only one class has results


def test_highest_and_lowest_need_two_scored_classes_that_differ():
    rows = [_row('5A', 5, 10, ot=9, wt=1), _row('5B', 5, 10, ot=3, wt=7), _row('6A', 6, 10, ot=6, wt=4)]
    view = build_subject_view(rows, 'maths')
    assert view['highest'] == '5A' and view['lowest'] == '5B'
    level = build_subject_view([_row('5A', 5, 10, ot=5, wt=5), _row('5B', 5, 10, ot=5, wt=5)], 'maths')
    assert level['highest'] is None and level['lowest'] is None


def test_no_classes_gives_an_empty_but_valid_view():
    view = build_subject_view([], 'maths')
    assert view['rows'] == [] and view['year_groups'] == [] and view['whole_school']['scored'] == 0


# ---- pages ---------------------------------------------------------------------------------

def _result(app, ids, pupil_id, school, band, percent, subject='maths', term='autumn'):
    with app.app_context():
        db.session.add(SubjectResult(pupil_id=pupil_id, school_id=ids[school], academic_year='2026/27', term=term,
                                     subject=subject, combined_percent=percent, band_label=band))
        db.session.commit()


def _get(app, ids, path, user='admin', **query):
    client = app.test_client(); login(client, ids[user])
    return client.get(path, query_string=query)


def test_subject_page_shows_this_schools_classes_only(world):  # noqa: F811
    app, ids = world
    _result(app, ids, ids['pupils'][0], 'a', 'On Track', 70.0)
    _result(app, ids, ids['pupils'][1], 'a', 'Working Towards', 30.0)
    _result(app, ids, ids['other_pupil'], 'b', 'On Track', 90.0)  # another school: must not count
    response = _get(app, ids, '/admin/reports/subject', subject='maths', academic_year='2026/27', term='autumn')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '1 of 2 pupils with a result' in html and '50.0%' in html
    assert 'Year 5' in html and 'Oak' in html


def test_subject_page_with_no_results_still_loads(world):  # noqa: F811
    app, ids = world
    response = _get(app, ids, '/admin/reports/subject', subject='reading', academic_year='2026/27')
    assert response.status_code == 200 and 'No results yet' in response.get_data(as_text=True)


def test_subject_page_is_admin_only_and_rejects_bad_input(world):  # noqa: F811
    app, ids = world
    assert _get(app, ids, '/admin/reports/subject', user='teacher').status_code == 403
    assert _get(app, ids, '/admin/reports/subject', subject='art').status_code == 400
    assert _get(app, ids, '/admin/reports/subject', term='christmas').status_code == 400


def test_admin_dashboard_shows_entry_strip_and_new_sidebar_links(world):  # noqa: F811
    app, ids = world
    response = _get(app, ids, '/dashboard/admin')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="entry-progress"' in html and 'class subjects have every score in' in html
    for link in ('/admin/reports/subject', '/admin/reports/scores-checklist', '/admin/reports/governor-summary', '/admin/reports/export-centre'):
        assert link in html


def test_teacher_dashboard_keeps_attention_first_and_folds_the_charts(world):  # noqa: F811
    app, ids = world
    html = _get(app, ids, '/dashboard/teacher', user='teacher').get_data(as_text=True)
    assert 'id="subjectCharts"' in html and 'Show subject charts' in html
    assert html.index('id="needs-attention"') < html.index('id="subjectCharts"')
