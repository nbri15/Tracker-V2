"""Anonymised governor / SLT report logic. Pure functions: no database, no pupil names.

Small groups are hidden. A group is hidden together with its partner group (for example
Pupil Premium and non-Pupil Premium), so a hidden number cannot be worked out by subtraction.
This reduces the chance of identifying a child; it is not a guarantee.
"""
from __future__ import annotations

MIN_GROUP = 5
HIDDEN = '<5'
BAND_WT, BAND_OT, BAND_GD = 'Working Towards', 'On Track', 'Exceeding'


def _gender(value):
    text = (value or '').strip().lower()
    return 'Female' if text in {'f', 'female', 'girl'} else 'Male' if text in {'m', 'male', 'boy'} else None


# Each pair: (measure, label for the first side, label for the second side, test on a pupil dict)
PAIRS = [
    ('Pupil Premium', 'Pupil Premium', 'Not Pupil Premium', lambda p: bool(p['pupil_premium'])),
    ('SEND', 'SEND', 'No SEND', lambda p: bool(p['send'])),
    ('Gender', 'Female', 'Male', lambda p: _gender(p['gender']) == 'Female'),
]


def _pct(part, whole):
    return f'{round(part / whole * 100, 1)}%'


def _split(pupils, test, measure):
    """Return the two sides of a pair. Pupils with an unrecognised gender are left out of the gender pair."""
    if measure == 'Gender':
        pupils = [p for p in pupils if _gender(p['gender'])]
    return [p for p in pupils if test(p)], [p for p in pupils if not test(p)]


def cohort_rows(pupils, minimum=MIN_GROUP):
    rows = [['Cohort', 'All pupils in this report', 'All', len(pupils) if len(pupils) >= minimum else HIDDEN, '', '', '', '']]
    for measure, first, second, test in PAIRS:
        side_a, side_b = _split(pupils, test, measure)
        hide = len(side_a) < minimum or len(side_b) < minimum
        for label, side in ((first, side_a), (second, side_b)):
            rows.append(['Cohort', measure, label, HIDDEN if hide else len(side), '', '', '', ''])
    return rows


def _band_cells(bands, minimum):
    if len(bands) < minimum:
        return [HIDDEN, HIDDEN, HIDDEN, HIDDEN, HIDDEN]
    n = len(bands)
    wt, ot, gd = (sum(1 for b in bands if b == name) for name in (BAND_WT, BAND_OT, BAND_GD))
    return [n, _pct(wt, n), _pct(ot, n), _pct(gd, n), _pct(ot + gd, n)]


def attainment_rows(subject_label, term_label, pupils, bands_by_pupil, minimum=MIN_GROUP):
    """pupils: list of dicts; bands_by_pupil: pupil id -> band label for pupils who have a score."""
    scored = [p for p in pupils if p['id'] in bands_by_pupil]
    measure = f'{subject_label} · {term_label}'
    rows = [['Attainment', measure, 'All'] + _band_cells([bands_by_pupil[p['id']] for p in scored], minimum)]
    for pair_measure, first, second, test in PAIRS:
        side_a, side_b = _split(scored, test, pair_measure)
        hide = len(side_a) < minimum or len(side_b) < minimum
        for label, side in ((first, side_a), (second, side_b)):
            cells = [HIDDEN] * 5 if hide else _band_cells([bands_by_pupil[p['id']] for p in side], minimum)
            rows.append(['Attainment', measure, label] + cells)
    return rows


def support_rows(subject_label, status_counts, minimum=MIN_GROUP):
    """status_counts: dict with improved / little_change / declined / awaiting (+ no_baseline) for active support."""
    total = sum(status_counts.values())
    if total == 0:
        return []
    labels = [('Pupils with active support', total),
              ('Improved since support began', status_counts.get('improved', 0)),
              ('Little change', status_counts.get('little_change', 0)),
              ('Declined', status_counts.get('declined', 0)),
              ('Waiting for next assessment', status_counts.get('awaiting', 0) + status_counts.get('no_baseline', 0))]
    hide_all = total < minimum
    rows = []
    for label, count in labels:
        shown = HIDDEN if hide_all or (label != labels[0][0] and 0 < count < minimum) else count
        rows.append(['Support', subject_label, label, shown, '', '', '', ''])
    return rows
