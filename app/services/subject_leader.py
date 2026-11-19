"""Subject leader view: one subject across every class, plus year-group totals. Read-only.

Works on the class rows the admin dashboard already builds (``build_class_overview_rows``),
so there is no new query logic here - only arrangement and arithmetic.
"""
from __future__ import annotations


def _percent(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def _totals(summaries) -> dict:
    """Combine several class summaries for one subject into one set of counts."""
    working_towards = sum(s['working_towards'] for s in summaries)
    on_track = sum(s['on_track'] for s in summaries)
    exceeding = sum(s['exceeding'] for s in summaries)
    scored = working_towards + on_track + exceeding
    return {
        'scored': scored,
        'working_towards': working_towards,
        'on_track': on_track,
        'exceeding': exceeding,
        'on_track_plus': on_track + exceeding,
        'working_towards_percent': _percent(working_towards, scored),
        'on_track_percent': _percent(on_track, scored),
        'exceeding_percent': _percent(exceeding, scored),
        'on_track_plus_percent': _percent(on_track + exceeding, scored),
    }


def build_subject_view(class_rows: list[dict], subject: str) -> dict:
    """Arrange class rows for one subject.

    Returns ``rows`` (one per class, in year order), ``year_groups`` (totals per year group),
    ``whole_school`` (totals for everything shown) and ``highest`` / ``lowest`` class names by
    on-track-or-better percentage (only among classes that have scores, and only when there are
    at least two of them so the comparison means something).
    """
    rows = []
    for row in sorted(class_rows, key=lambda r: (r['year_group'], r['class_name'].lower())):
        summary = row['subjects'][subject]
        totals = _totals([summary])
        rows.append({
            'class_id': row['class_id'],
            'class_name': row['class_name'],
            'year_group': row['year_group'],
            'teacher_name': row['teacher_name'],
            'pupil_count': row['pupil_count'],
            'active_interventions': row.get('active_interventions', 0),
            'term_label': summary.get('term_label') or 'No data',
            'average_percent': summary.get('average_percent'),
            'missing': max(row['pupil_count'] - totals['scored'], 0),
            **totals,
        })

    by_year: dict[int, list[dict]] = {}
    for row in class_rows:
        by_year.setdefault(row['year_group'], []).append(row)
    year_groups = []
    for year_group in sorted(by_year):
        group_rows = by_year[year_group]
        totals = _totals([r['subjects'][subject] for r in group_rows])
        year_groups.append({
            'year_group': year_group,
            'classes': len(group_rows),
            'pupil_count': sum(r['pupil_count'] for r in group_rows),
            **totals,
        })

    whole_school = _totals([r['subjects'][subject] for r in class_rows])
    whole_school['pupil_count'] = sum(r['pupil_count'] for r in class_rows)
    whole_school['active_interventions'] = sum(r.get('active_interventions', 0) for r in class_rows)

    scored_rows = [r for r in rows if r['scored'] > 0]
    highest = lowest = None
    if len(scored_rows) >= 2:
        ranked = sorted(scored_rows, key=lambda r: (-r['on_track_plus_percent'], r['class_name'].lower()))
        highest, lowest = ranked[0]['class_name'], ranked[-1]['class_name']
        if ranked[0]['on_track_plus_percent'] == ranked[-1]['on_track_plus_percent']:
            highest = lowest = None  # all level - nothing to point at

    return {'rows': rows, 'year_groups': year_groups, 'whole_school': whole_school,
            'highest': highest, 'lowest': lowest}
