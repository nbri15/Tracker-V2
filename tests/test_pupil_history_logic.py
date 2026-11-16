"""Pure logic for pupil timelines and progress tables. Fictional data only; no database needed."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location('pupil_history', pathlib.Path(__file__).parents[1] / 'app' / 'services' / 'pupil_history.py')
ph = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ph)


def r(subject, year, term, percent, band='On Track'):
    return {'subject': subject, 'academic_year': year, 'term': term, 'percent': percent, 'band': band}


RESULTS = [r('maths', '2025/26', 'summer', 60), r('maths', '2025/26', 'autumn', 50, 'Working Towards'),
           r('maths', '2026/27', 'autumn', 58), r('reading', '2025/26', 'autumn', 70)]


def test_columns_are_in_time_order_and_changes_follow_the_subject():
    columns, rows = ph.progress_table(RESULTS, ['maths', 'reading'])
    assert columns == [('2025/26', 'autumn'), ('2025/26', 'summer'), ('2026/27', 'autumn')]
    maths = rows[0]['cells']
    assert [c['percent'] for c in maths] == [50, 60, 58]
    assert [c['change'] for c in maths] == [None, 10, -2]
    reading = rows[1]['cells']
    assert reading[0]['percent'] == 70 and reading[1] is None and reading[2] is None


def test_missing_scores_are_gaps_not_zero():
    _, rows = ph.progress_table([r('maths', '2026/27', 'autumn', None), r('maths', '2026/27', 'spring', 40)], ['maths'])
    assert [c['percent'] for c in rows[0]['cells']] == [40]


def test_last_keeps_recent_terms_but_change_still_uses_earlier_score():
    columns, rows = ph.progress_table(RESULTS, ['maths'], last=1)
    assert columns == [('2026/27', 'autumn')] and rows[0]['cells'][0]['change'] == -2


def test_term_text_is_case_insensitive():
    columns, _ = ph.progress_table([r('maths', '2026/27', 'Autumn', 50), r('maths', '2026/27', ' autumn ', 55)], ['maths'])
    assert columns == [('2026/27', 'autumn')]


def test_timeline_is_newest_first_and_mixes_events():
    supports = [{'academic_year': '2025/26', 'term': 'autumn', 'subject': 'maths', 'programmes': ['Maths booster'], 'active': False,
                 'status_label': 'Improved', 'change': 10.0}]
    moves = [{'academic_year': '2025/26', 'class_name': 'Oak', 'year_group': 4}, {'academic_year': '2026/27', 'class_name': 'Elm', 'year_group': 5}]
    events = ph.build_timeline(RESULTS, supports, moves, {'maths': 'Maths', 'reading': 'Reading'})
    assert events[0]['kind'] == 'results' and events[0]['academic_year'] == '2026/27'
    assert events[-1]['title'].startswith('In class Oak (Year 4)')
    support = next(e for e in events if e['kind'] == 'support')
    assert 'Maths booster' in support['title'] and '(closed)' in support['title'] and support['lines'] == ['Improved (+10)']
    autumn = next(e for e in events if e['kind'] == 'results' and e['academic_year'] == '2025/26' and e['term_label'] == 'Autumn')
    assert 'Maths: 50% Working Towards' in autumn['lines'] and 'Reading: 70% On Track' in autumn['lines']


def test_individual_support_without_a_programme_is_named_plainly():
    event = ph.build_timeline([], [{'academic_year': '2026/27', 'term': 'spring', 'subject': 'spag', 'programmes': [], 'active': True,
                                    'status_label': None, 'change': None}], [])[0]
    assert event['title'] == 'Support started: spag · individual support'
