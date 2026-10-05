"""Authoritative result writes, assessment health and scoped setup impact."""
from __future__ import annotations
import hashlib
import json
from types import SimpleNamespace
from sqlalchemy import select
from app.extensions import db
from app.models import AssessmentConfiguration, AssessmentReview, AuditLog, PupilClassHistory, School, SubjectResult
from app.utils import log_audit_event
from .assessments import AssessmentValidationError, compute_subject_result_values, get_subject_setting, resolve_subject_band_label

CONFIG_FIELDS = ('paper_1_name', 'paper_1_max', 'paper_2_name', 'paper_2_max', 'combined_max', 'below_are_threshold_percent', 'on_track_threshold_percent', 'exceeding_threshold_percent')


def configuration_values(setting):
    return {key: getattr(setting, key) for key in CONFIG_FIELDS}


def cohort_year_group(pupil, academic_year):
    with db.session.no_autoflush:
        history = PupilClassHistory.query.filter_by(school_id=pupil.school_id, pupil_id=pupil.id, academic_year=academic_year).first()
    return history.year_group if history else (pupil.school_class.year_group if pupil.school_class else pupil.join_year_group)


def setting_for_result(result, fallback=None):
    if result.configuration_snapshot:
        return SimpleNamespace(**result.configuration_snapshot)
    with db.session.no_autoflush:
        return fallback or get_subject_setting(cohort_year_group(result.pupil, result.academic_year), result.subject, result.term, result.academic_year, school_id=result.pupil.school_id)


def apply_result(result, setting, paper_1, paper_2, *, cohort=None, assessment_year_group=None, source=None):
    """Validate, derive and snapshot together. Never commit inside the writer."""
    if result.pupil and setting.school_id is not None and result.pupil.school_id != setting.school_id:
        raise AssessmentValidationError('This pupil does not belong to the selected school.')
    computed = compute_subject_result_values(setting, paper_1, paper_2)
    cohort = cohort if cohort is not None else cohort_year_group(result.pupil, result.academic_year)
    test_year = assessment_year_group if assessment_year_group is not None else cohort
    result.paper_1_score, result.paper_2_score = paper_1, paper_2
    result.combined_score = computed['combined_score']
    result.combined_percent = computed['combined_percent']
    result.band_label = resolve_subject_band_label(percent=computed['combined_percent'], setting=setting, pupil_year_group=cohort, assessment_year_group=test_year)
    result.school_id = setting.school_id
    result.assessment_year_group = test_year
    result.cohort_year_group = cohort
    result.configuration_snapshot = configuration_values(setting) | {'school_id': setting.school_id}
    if source:
        result.source = source
    db.session.add(result)
    return result


def scope_results(school_id, academic_year, year_group, subject, term):
    rows = SubjectResult.query.filter_by(school_id=school_id, academic_year=academic_year, subject=subject, term=term).all()
    return [row for row in rows if (row.cohort_year_group if row.cohort_year_group is not None else cohort_year_group(row.pupil, academic_year)) == year_group]


def assessment_health(pupils, results, setting):
    reasons = []
    try:
        values = configuration_values(setting)
        if any(values[key] is None or values[key] <= 0 for key in ('paper_1_max', 'paper_2_max', 'combined_max')):
            raise AssessmentValidationError('Maximum marks are missing or invalid.')
        if values['combined_max'] != values['paper_1_max'] + values['paper_2_max']:
            raise AssessmentValidationError('Combined maximum does not match paper maxima.')
        if not 0 <= values['below_are_threshold_percent'] <= values['exceeding_threshold_percent'] <= 100:
            raise AssessmentValidationError('Expected Standard / Greater Depth thresholds are invalid.')
    except (ValueError, TypeError) as exc:
        return {'label': 'Configuration problem', 'theme': 'danger', 'valid': 0, 'total': len(pupils), 'reasons': [str(exc)]}
    valid = 0
    entered = 0
    for pupil in pupils:
        row = results.get(pupil.id)
        if not row or (row.paper_1_score is None and row.paper_2_score is None):
            reasons.append(f'{pupil.full_name}: both paper scores are missing.')
            continue
        entered += 1
        try:
            derived = compute_subject_result_values(setting_for_result(row, setting), row.paper_1_score, row.paper_2_score)
            if derived['combined_percent'] is None:
                reasons.append(f'{pupil.full_name}: one paper score is missing.')
            elif row.combined_percent is None or row.band_label is None:
                reasons.append(f'{pupil.full_name}: saved outcome needs an explicit recalculation in Assessment Setup.')
            else:
                valid += 1
        except AssessmentValidationError as exc:
            reasons.append(f'{pupil.full_name}: {exc}')
    label = 'Complete' if valid == len(pupils) and pupils else ('Draft' if not entered else 'Incomplete')
    return {'label': label, 'theme': {'Complete': 'success', 'Draft': 'info', 'Incomplete': 'warning'}[label], 'valid': valid, 'total': len(pupils), 'reasons': reasons}


def setup_impact(school_id, academic_year, year_group, subject, term, proposed):
    rows = scope_results(school_id, academic_year, year_group, subject, term)
    changed = []
    errors = []
    setting = SimpleNamespace(school_id=school_id, **proposed)
    for row in rows:
        try:
            computed = compute_subject_result_values(setting, row.paper_1_score, row.paper_2_score)
            band = resolve_subject_band_label(percent=computed['combined_percent'], setting=setting, pupil_year_group=year_group, assessment_year_group=row.assessment_year_group)
            if band != row.band_label:
                changed.append({'pupil': row.pupil.full_name, 'current': row.band_label or 'Missing', 'proposed': band or 'Missing'})
        except AssessmentValidationError as exc:
            errors.append(f'{row.pupil.full_name}: {exc}')
    return {'checked': len(rows), 'changed': len(changed), 'unchanged': len(rows) - len(changed), 'rows': changed, 'errors': errors}


def apply_setup(payload):
    school_id = payload['school_id']
    identity = {key: payload[key] for key in ('school_id', 'academic_year', 'year_group', 'subject', 'term')}
    setting = AssessmentConfiguration.query.filter_by(**identity).first()
    created = setting is None
    setting = setting or AssessmentConfiguration(**identity)
    old = configuration_values(get_subject_setting(payload['year_group'], payload['subject'], payload['term'], payload['academic_year'], school_id=school_id))
    for key in CONFIG_FIELDS:
        setattr(setting, key, payload['proposed'][key])
    db.session.add(setting)
    rows = scope_results(school_id, payload['academic_year'], payload['year_group'], payload['subject'], payload['term'])
    for row in rows:
        apply_result(row, setting, row.paper_1_score, row.paper_2_score, cohort=payload['year_group'], assessment_year_group=row.assessment_year_group)
    from .interventions import sync_auto_interventions
    from app.models import SchoolClass
    from .assessments import get_school_working_academic_year
    if payload['academic_year'] == get_school_working_academic_year(school_id).name:
        for school_class in SchoolClass.query.filter_by(school_id=school_id, year_group=payload['year_group'], is_active=True).all():
            sync_auto_interventions(school_class, payload['subject'], payload['term'], payload['academic_year'], setting.below_are_threshold_percent)
    db.session.flush()
    action = 'assessment_created' if created else 'assessment_configuration_changed'
    log_audit_event(action, 'assessment_configuration', setting.id, school_id=school_id, details=json.dumps(identity | {'before': old, 'after': payload['proposed']}))
    log_audit_event('assessment_results_recalculated', 'assessment_configuration', setting.id, school_id=school_id, details=f"{len(rows)} results recalculated for {payload['academic_year']} {payload['subject']} {payload['term']}")
    if old['below_are_threshold_percent'] != setting.below_are_threshold_percent or old['exceeding_threshold_percent'] != setting.exceeding_threshold_percent:
        log_audit_event('assessment_threshold_changed', 'assessment_configuration', setting.id, school_id=school_id, details=json.dumps({'before': old, 'after': payload['proposed'], 'academic_year': payload['academic_year']}))
    return len(rows)


def raw_boundary(setting, threshold):
    # The existing band rule compares the one-decimal displayed percentage.
    # Iterate exact marks so the displayed boundary matches that rule, including 0%.
    if SubjectResult.calculate_percent(setting.combined_max, setting.combined_max) < threshold:
        return setting.combined_max + 1
    low, high = 0, setting.combined_max
    while low < high:
        middle = (low + high) // 2
        if SubjectResult.calculate_percent(middle, setting.combined_max) >= threshold:
            high = middle
        else:
            low = middle + 1
    return low


def school_fingerprint(school_id):
    """Conservative conflict guard for reviewed imports/settings/manual entry."""
    state = []
    for table in sorted(db.metadata.tables.values(), key=lambda table: table.name):
        if 'school_id' not in table.c or table.name in {'audit_logs', 'assessment_reviews'}:
            continue
        rows = db.session.execute(select(table).where(table.c.school_id == school_id).order_by(*table.primary_key.columns)).mappings().all()
        state.append((table.name, [dict(row) for row in rows]))
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def lock_school(school_id):
    db.session.execute(select(School.id).where(School.id == school_id).with_for_update()).scalar_one()


def assessment_history(school_id, limit=30):
    return AuditLog.query.filter(AuditLog.school_id == school_id, AuditLog.action.like('assessment_%')).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
