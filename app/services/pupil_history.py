"""A pupil's history across terms and years. Pure functions: no database access.

Callers pass plain dicts so this can be tested without a database.
"""
from __future__ import annotations

TERM_ORDER = {'autumn': 1, 'spring': 2, 'summer': 3}
TERM_LABELS = {'autumn': 'Autumn', 'spring': 'Spring', 'summer': 'Summer'}


def position(academic_year, term):
    return (academic_year or '', TERM_ORDER.get((term or '').strip().lower(), 0))


def term_label(term):
    return TERM_LABELS.get((term or '').strip().lower(), (term or '').title())


def _fmt_change(change):
    if change is None:
        return ''
    text = f'{abs(change):.1f}'.rstrip('0').rstrip('.')
    return f' ({"+" if change > 0 else "-" if change < 0 else "±"}{text})'


def progress_table(results, subjects, last=None):
    """Rows per subject, one cell per assessment term in time order.

    results: dicts with subject, academic_year, term, percent, band. A missing score is None.
    Each cell has percent, band and change (points since that subject's previous score).
    ``last`` keeps only the most recent N assessment terms (the change still uses earlier scores).
    """
    scored = [r for r in results if r.get('percent') is not None]
    columns = sorted({(r['academic_year'], (r['term'] or '').strip().lower()) for r in scored}, key=lambda c: position(*c))
    rows = []
    for subject in subjects:
        by_col = {}
        for r in scored:
            if r['subject'] == subject:
                by_col[(r['academic_year'], (r['term'] or '').strip().lower())] = r  # later rows win
        cells, previous = [], None
        for col in columns:
            r = by_col.get(col)
            if r is None:
                cells.append(None)
                continue
            percent = round(float(r['percent']), 1)
            cells.append({'percent': percent, 'band': r.get('band'), 'change': None if previous is None else round(percent - previous, 1)})
            previous = percent
        rows.append({'subject': subject, 'cells': cells})
    if last:
        columns = columns[-last:]
        for row in rows:
            row['cells'] = row['cells'][-last:]
    return columns, rows


def build_timeline(results, supports, moves, subject_labels=None):
    """Newest-first list of events: class moves, support, and each term's results.

    supports: dicts with academic_year, term, subject, programmes (list of names), active (bool),
              status_label, change (points or None).
    moves:    dicts with academic_year, class_name, year_group.
    """
    labels = subject_labels or {}
    events = []
    for move in moves:
        group = move.get('year_group')
        where = 'Reception' if group == 0 else f'Year {group}' if group is not None else ''
        events.append({'sort': (move['academic_year'] or '', 0, 0), 'academic_year': move['academic_year'], 'term_label': '',
                       'kind': 'class', 'title': f'In class {move["class_name"]}' + (f' ({where})' if where else ''), 'lines': []})
    for support in supports:
        pos = position(support['academic_year'], support['term'])
        programmes = ', '.join(support.get('programmes') or []) or 'individual support'
        subject = labels.get(support['subject'], support['subject'])
        lines = [f'{support["status_label"]}{_fmt_change(support.get("change"))}'] if support.get('status_label') else []
        events.append({'sort': (pos[0], pos[1], 1), 'academic_year': support['academic_year'], 'term_label': term_label(support['term']),
                       'kind': 'support', 'title': f'Support started: {subject} · {programmes}' + ('' if support.get('active') else ' (closed)'), 'lines': lines})
    columns, rows = progress_table(results, sorted({r['subject'] for r in results}))
    for index, (year, term) in enumerate(columns):
        lines = []
        for row in rows:
            cell = row['cells'][index]
            if cell:
                lines.append(f'{labels.get(row["subject"], row["subject"])}: {cell["percent"]:g}%' + (f' {cell["band"]}' if cell['band'] else '') + _fmt_change(cell['change']))
        if lines:
            pos = position(year, term)
            events.append({'sort': (pos[0], pos[1], 2), 'academic_year': year, 'term_label': term_label(term), 'kind': 'results',
                           'title': 'Assessment results', 'lines': lines})
    return sorted(events, key=lambda e: e['sort'], reverse=True)
