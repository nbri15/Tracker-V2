"""Pure logic for the anonymised governor report. Fictional data only; no database needed."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location('governor_report', pathlib.Path(__file__).parents[1] / 'app' / 'services' / 'governor_report.py')
gr = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gr)


def pupils(n, pp=lambda i: False, send=lambda i: False):
    return [{'id': i, 'pupil_premium': pp(i), 'send': send(i), 'gender': 'Female' if i % 2 else 'Male'} for i in range(n)]


def bands(n, wt=0, gd=0):
    return {i: ('Working Towards' if i < wt else 'Exceeding' if i >= n - gd else 'On Track') for i in range(n)}


def test_percentages_for_the_whole_group():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(20), bands(20, wt=5, gd=3))
    assert rows[0][2:] == ['All', 20, '25.0%', '60.0%', '15.0%', '75.0%']


def test_small_group_is_hidden_together_with_its_partner():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(30, send=lambda i: i < 3), bands(30))
    send = {r[2]: r[3:] for r in rows if r[2] in {'SEND', 'No SEND'}}
    assert send['SEND'] == [gr.HIDDEN] * 5 and send['No SEND'] == [gr.HIDDEN] * 5


def test_group_of_exactly_the_minimum_is_shown():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(30, send=lambda i: i < 5), bands(30))
    assert {r[2]: r[3] for r in rows}['SEND'] == 5


def test_pupils_without_a_score_are_not_counted():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(20), {i: 'On Track' for i in range(8)})
    assert rows[0][3] == 8


def test_everything_hidden_when_fewer_than_minimum_scored():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(20), {0: 'On Track', 1: 'On Track'})
    assert all(cell == gr.HIDDEN for row in rows for cell in row[3:])


def test_cohort_rows_hide_small_send_group_and_partner():
    rows = {(r[1], r[2]): r[3] for r in gr.cohort_rows(pupils(30, send=lambda i: i < 2, pp=lambda i: i < 10))}
    assert rows[('SEND', 'SEND')] == gr.HIDDEN and rows[('SEND', 'No SEND')] == gr.HIDDEN
    assert rows[('Pupil Premium', 'Pupil Premium')] == 10


def test_support_rows_hide_small_numbers_and_never_contain_names():
    rows = gr.support_rows('Maths', {'improved': 6, 'little_change': 2, 'declined': 0, 'awaiting': 3})
    shown = {r[2]: r[3] for r in rows}
    assert shown['Pupils with active support'] == 11 and shown['Improved since support began'] == 6
    assert shown['Little change'] == gr.HIDDEN and shown['Declined'] == 0
    assert gr.support_rows('Maths', {'improved': 2})[0][3] == gr.HIDDEN
    assert gr.support_rows('Maths', {}) == []


def test_one_below_the_minimum_is_hidden_everywhere():
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(30), {i: 'On Track' for i in range(4)})
    assert rows[0][3:] == [gr.HIDDEN] * 5
    rows = gr.attainment_rows('Maths', 'Autumn', pupils(30, send=lambda i: i < 4), bands(30))
    assert {r[2]: r[3] for r in rows}['SEND'] == gr.HIDDEN
    assert {(r[1], r[2]): r[3] for r in gr.cohort_rows(pupils(30, send=lambda i: i < 4))}[('SEND', 'SEND')] == gr.HIDDEN
