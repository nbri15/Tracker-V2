"""Did an intervention help?  Baseline versus the next assessment.

Teachers enter nothing extra.  When support begins we remember the pupil's score for
that term (the baseline).  The follow-up is the pupil's score in the next assessment
for the same subject, which teachers enter anyway.

The comparison rules below are plain functions with no database access so they can be
tested on their own.  ``outcomes_for`` is the small database layer on top of them.
"""

from __future__ import annotations

TERM_ORDER = {'autumn': 1, 'spring': 2, 'summer': 3}

# A change smaller than this many percentage points is reported as "little change"
# rather than as an improvement or decline, because test-to-test scores naturally wobble.
MEANINGFUL_CHANGE_POINTS = 2.0

STATUS_LABELS = {
    'improved': 'Improved',
    'little_change': 'Little change',
    'declined': 'Declined',
    'awaiting': 'Awaiting next assessment',
    'no_baseline': 'No baseline score',
}
# Bootstrap badge colours for each status.
STATUS_BADGES = {
    'improved': 'text-bg-success',
    'little_change': 'text-bg-secondary',
    'declined': 'text-bg-danger',
    'awaiting': 'text-bg-light border',
    'no_baseline': 'text-bg-light border',
}

NO_PROGRAMME_LABEL = 'Individual support (no programme)'


def term_position(academic_year, term):
    """Sortable position of an assessment: later assessments sort higher."""
    return (academic_year or '', TERM_ORDER.get((term or '').strip().lower(), 0))


def _row_sort_key(row):
    updated = getattr(row, 'updated_at', None)
    stamp = updated.timestamp() if updated is not None else 0.0
    return (stamp, getattr(row, 'id', 0) or 0)


def latest_row_for_term(rows, academic_year, term):
    """The most recently saved result for exactly this year and term, or None."""
    matches = [row for row in rows
               if row.academic_year == academic_year and (row.term or '').lower() == (term or '').lower()
               and row.combined_percent is not None]
    return max(matches, key=_row_sort_key) if matches else None


def pick_follow_up(rows, academic_year, term):
    """The first assessment after (academic_year, term) that has a percentage score."""
    start = term_position(academic_year, term)
    later = [row for row in rows
             if row.combined_percent is not None and term_position(row.academic_year, row.term) > start]
    if not later:
        return None
    earliest = min(term_position(row.academic_year, row.term) for row in later)
    # If a term was saved more than once, the most recently saved score is the one that counts.
    return max((row for row in later if term_position(row.academic_year, row.term) == earliest),
               key=_row_sort_key)


def classify_change(change):
    if change is None:
        return None
    if change >= MEANINGFUL_CHANGE_POINTS:
        return 'improved'
    if change <= -MEANINGFUL_CHANGE_POINTS:
        return 'declined'
    return 'little_change'


def compute_outcome(*, baseline_percent, baseline_source, follow_percent=None,
                    follow_threshold=None, follow_term=None, follow_year=None, baseline_band=None):
    """Combine a baseline and a follow-up into the figures the pages display."""
    change = None
    if baseline_percent is not None and follow_percent is not None:
        change = round(follow_percent - baseline_percent, 1)
    if baseline_percent is None:
        status = 'no_baseline'
    elif follow_percent is None:
        status = 'awaiting'
    else:
        status = classify_change(change)
    met = None
    if follow_percent is not None and follow_threshold is not None:
        met = follow_percent >= follow_threshold
    return {
        'status': status,
        'status_label': STATUS_LABELS[status],
        'badge': STATUS_BADGES[status],
        'baseline_percent': None if baseline_percent is None else round(baseline_percent, 1),
        'baseline_band': baseline_band,
        'baseline_source': baseline_source if baseline_percent is not None else None,
        'follow_percent': None if follow_percent is None else round(follow_percent, 1),
        'follow_term': follow_term,
        'follow_year': follow_year,
        'change': change,
        'met_threshold': met,
    }


def format_percent(value):
    if value is None:
        return '—'
    return f'{value:.1f}'.rstrip('0').rstrip('.') + '%'


def format_change(change):
    if change is None:
        return '—'
    text = f'{abs(change):.1f}'.rstrip('0').rstrip('.')
    sign = '+' if change > 0 else ('-' if change < 0 else '')
    return f'{sign}{text} points'


def summarise_groups(pairs):
    """Roll outcomes up by group, e.g. by programme.

    ``pairs`` is an iterable of ``(group_name, outcome)``.  Only pupils who have both a
    baseline and a follow-up count towards the averages, so nobody is judged early.
    """
    groups = {}
    for name, outcome in pairs:
        group = groups.setdefault(name, {'name': name, 'pupils': 0, 'reassessed': 0, 'improved': 0,
                                         'little_change': 0, 'declined': 0, 'met_threshold': 0,
                                         '_changes': []})
        group['pupils'] += 1
        if outcome['change'] is not None:
            group['reassessed'] += 1
            group['_changes'].append(outcome['change'])
            group[outcome['status']] += 1
            if outcome['met_threshold']:
                group['met_threshold'] += 1
    summary = []
    for group in groups.values():
        changes = group.pop('_changes')
        group['average_change'] = round(sum(changes) / len(changes), 1) if changes else None
        summary.append(group)
    return sorted(summary, key=lambda item: (item['name'] == NO_PROGRAMME_LABEL, item['name'].casefold()))


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

def capture_baseline(intervention):
    """Remember the pupil's score for the intervention's own term, once.

    Never overwrites a baseline that was already recorded, and never invents one: if the
    pupil has no percentage for that term the baseline stays empty.
    """
    from app.extensions import db
    from app.models import SubjectResult

    if intervention.baseline_percent is not None:
        return
    with db.session.no_autoflush:
        rows = SubjectResult.query.filter_by(
            pupil_id=intervention.pupil_id, subject=intervention.subject,
            term=intervention.term, academic_year=intervention.academic_year).all()
    row = latest_row_for_term(rows, intervention.academic_year, intervention.term)
    if row is not None:
        intervention.baseline_percent = float(row.combined_percent)
        intervention.baseline_band = row.band_label


def outcomes_for(interventions):
    """Map intervention id -> outcome dict, using one query for all results."""
    from app.models import SubjectResult
    from app.services.assessment_reliability import setting_for_result

    interventions = list(interventions)
    if not interventions:
        return {}
    pupil_ids = {row.pupil_id for row in interventions}
    subjects = {row.subject for row in interventions}
    by_pupil_subject = {}
    for result in SubjectResult.query.filter(
            SubjectResult.pupil_id.in_(pupil_ids), SubjectResult.subject.in_(subjects),
            SubjectResult.combined_percent.isnot(None)).all():
        by_pupil_subject.setdefault((result.pupil_id, result.subject), []).append(result)

    outcomes = {}
    for record in interventions:
        rows = by_pupil_subject.get((record.pupil_id, record.subject), [])
        if record.baseline_percent is not None:
            baseline, source, band = record.baseline_percent, 'recorded', record.baseline_band
        else:
            # Records made before baselines were saved: use the term's score as it stands now.
            same_term = latest_row_for_term(rows, record.academic_year, record.term)
            baseline = float(same_term.combined_percent) if same_term else None
            source, band = 'estimated', (same_term.band_label if same_term else None)
        follow = pick_follow_up(rows, record.academic_year, record.term)
        threshold = None
        if follow is not None:
            try:
                threshold = float(setting_for_result(follow).below_are_threshold_percent)
            except Exception:  # a missing setting must never break the page
                threshold = None
        outcomes[record.id] = compute_outcome(
            baseline_percent=baseline, baseline_source=source, baseline_band=band,
            follow_percent=float(follow.combined_percent) if follow else None,
            follow_threshold=threshold,
            follow_term=follow.term if follow else None,
            follow_year=follow.academic_year if follow else None)
    return outcomes


def programme_summary(interventions, outcomes):
    """Impact by programme for the interventions in view."""
    pairs = []
    for record in interventions:
        outcome = outcomes.get(record.id)
        if outcome is None:
            continue
        programmes = record.programmes
        if programmes:
            pairs.extend((programme.name, outcome) for programme in programmes)
        else:
            pairs.append((NO_PROGRAMME_LABEL, outcome))
    return summarise_groups(pairs)
