"""Rules for judging whether an intervention helped. Pure logic, fictional numbers only."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.intervention_impact import (
    NO_PROGRAMME_LABEL, classify_change, compute_outcome, format_change, format_percent,
    latest_row_for_term, pick_follow_up, summarise_groups, term_position)


def row(year, term, percent, id=1, updated=None):
    return SimpleNamespace(academic_year=year, term=term, combined_percent=percent, id=id, updated_at=updated)


def test_terms_sort_in_school_order_across_years():
    assert term_position('2026/27', 'autumn') < term_position('2026/27', 'spring') < term_position('2026/27', 'summer')
    assert term_position('2026/27', 'summer') < term_position('2027/28', 'autumn')


def test_follow_up_is_the_next_assessment_not_the_latest_or_the_same_term():
    rows = [row('2026/27', 'autumn', 40), row('2026/27', 'spring', 50), row('2026/27', 'summer', 70)]
    assert pick_follow_up(rows, '2026/27', 'autumn').term == 'spring'
    assert pick_follow_up(rows, '2026/27', 'spring').term == 'summer'
    assert pick_follow_up(rows, '2026/27', 'summer') is None


def test_follow_up_can_be_in_the_next_academic_year():
    rows = [row('2026/27', 'summer', 40), row('2027/28', 'autumn', 55)]
    assert pick_follow_up(rows, '2026/27', 'summer').academic_year == '2027/28'


def test_follow_up_skips_terms_with_no_score_and_zero_is_a_real_score():
    rows = [row('2026/27', 'spring', None), row('2026/27', 'summer', 0)]
    found = pick_follow_up(rows, '2026/27', 'autumn')
    assert found.term == 'summer' and found.combined_percent == 0


def test_most_recently_saved_score_wins_when_a_term_was_saved_twice():
    old = row('2026/27', 'spring', 30, id=1, updated=datetime(2027, 1, 1))
    new = row('2026/27', 'spring', 45, id=2, updated=datetime(2027, 2, 1))
    assert pick_follow_up([old, new], '2026/27', 'autumn').combined_percent == 45
    assert latest_row_for_term([old, new], '2026/27', 'spring').combined_percent == 45


@pytest.mark.parametrize('change,expected', [
    (None, None), (2.0, 'improved'), (13.5, 'improved'), (1.9, 'little_change'),
    (0, 'little_change'), (-1.9, 'little_change'), (-2.0, 'declined'), (-20, 'declined')])
def test_change_classification(change, expected):
    assert classify_change(change) == expected


def test_outcome_improved_and_met_pass():
    outcome = compute_outcome(baseline_percent=40, baseline_source='recorded', follow_percent=55,
                              follow_threshold=50, follow_term='spring', follow_year='2026/27')
    assert outcome['status'] == 'improved' and outcome['change'] == 15.0 and outcome['met_threshold'] is True


def test_outcome_improved_but_still_below_pass():
    outcome = compute_outcome(baseline_percent=30, baseline_source='recorded', follow_percent=40, follow_threshold=50)
    assert outcome['status'] == 'improved' and outcome['met_threshold'] is False


def test_outcome_declined():
    assert compute_outcome(baseline_percent=60, baseline_source='recorded', follow_percent=50)['status'] == 'declined'


def test_nobody_is_judged_before_reassessment():
    outcome = compute_outcome(baseline_percent=40, baseline_source='recorded')
    assert outcome['status'] == 'awaiting' and outcome['change'] is None and outcome['met_threshold'] is None


def test_no_baseline_is_never_treated_as_zero():
    outcome = compute_outcome(baseline_percent=None, baseline_source='estimated', follow_percent=55)
    assert outcome['status'] == 'no_baseline' and outcome['change'] is None and outcome['baseline_source'] is None


def test_a_zero_baseline_is_a_real_baseline():
    outcome = compute_outcome(baseline_percent=0, baseline_source='recorded', follow_percent=10)
    assert outcome['status'] == 'improved' and outcome['change'] == 10.0


def test_formatting():
    assert format_percent(42.0) == '42%' and format_percent(42.5) == '42.5%' and format_percent(None) == '—'
    assert format_change(13.0) == '+13 points' and format_change(-2.5) == '-2.5 points'
    assert format_change(0) == '0 points' and format_change(None) == '—'


def test_programme_summary_counts_only_reassessed_pupils_in_averages():
    def make(**kw):
        return compute_outcome(baseline_source='recorded', follow_threshold=50, **kw)
    pairs = [
        ('Maths booster', make(baseline_percent=40, follow_percent=55)),   # +15, met
        ('Maths booster', make(baseline_percent=45, follow_percent=44)),   # -1, little change
        ('Maths booster', make(baseline_percent=30)),                      # not reassessed yet
        (NO_PROGRAMME_LABEL, make(baseline_percent=50, follow_percent=40)),  # -10 declined
    ]
    summary = {item['name']: item for item in summarise_groups(pairs)}
    booster = summary['Maths booster']
    assert booster['pupils'] == 3 and booster['reassessed'] == 2
    assert booster['improved'] == 1 and booster['little_change'] == 1 and booster['declined'] == 0
    assert booster['average_change'] == 7.0 and booster['met_threshold'] == 1
    assert summary[NO_PROGRAMME_LABEL]['declined'] == 1
    assert [item['name'] for item in summarise_groups(pairs)][-1] == NO_PROGRAMME_LABEL


def test_summary_with_nobody_reassessed_has_no_average():
    summary = summarise_groups([('Reading group', compute_outcome(baseline_percent=40, baseline_source='recorded'))])
    assert summary[0]['average_change'] is None and summary[0]['reassessed'] == 0
