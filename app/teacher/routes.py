"""Teacher assessment entry routes."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Intervention, Pupil, SatsResult, SatsWritingResult, SubjectResult, WritingResult
from app.services import (
    SATS_ASSESSMENT_POINTS,
    SATS_SUBJECTS,
    SORT_OPTIONS,
    TERMS,
    WRITING_BAND_CHOICES,
    AssessmentValidationError,
    AUTO_REASON,
    build_academic_year_options,
    build_gap_page_context,
    compute_subject_result_values,
    format_subject_name,
    get_current_academic_year,
    get_current_term,
    get_or_create_gap_template,
    get_sats_subject_summary,
    get_sats_writing_summary,
    get_subject_setting,
    parse_question_columns,
    recalculate_subject_results_for_scope,
    save_gap_scores,
    sync_auto_interventions,
    update_assessment_setting,
    validate_setting_payload,
)
from app.utils import get_primary_class_for_user, teacher_required

from . import teacher_bp


SUBJECT_META = {
    'maths': {'title': 'Maths'},
    'reading': {'title': 'Reading'},
    'spag': {'title': 'SPaG'},
    'writing': {'title': 'Writing'},
}


@teacher_bp.route('/maths', methods=['GET', 'POST'])
@login_required
@teacher_required
def maths():
    return render_subject_page('maths')


@teacher_bp.route('/reading', methods=['GET', 'POST'])
@login_required
@teacher_required
def reading():
    return render_subject_page('reading')


@teacher_bp.route('/spag', methods=['GET', 'POST'])
@login_required
@teacher_required
def spag():
    return render_subject_page('spag')


@teacher_bp.route('/writing', methods=['GET', 'POST'])
@login_required
@teacher_required
def writing():
    return render_writing_page()


@teacher_bp.route('/<subject>/gap', methods=['GET', 'POST'])
@login_required
@teacher_required
def gap_analysis(subject: str):
    if subject not in {'maths', 'reading', 'spag'}:
        flash('GAP analysis is only available for Maths, Reading, and SPaG.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    context = _base_subject_context(subject)
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/gap_analysis.html', rows=[], questions=[], template=None, max_total=0, **context)

    template = get_or_create_gap_template(school_class.year_group, subject, context['term'], context['academic_year'])
    pupils = context['pupils']

    if request.method == 'POST':
        try:
            template.paper_name = request.form.get('paper_name', '').strip() or None
            questions = parse_question_columns(request.form, template)
            db.session.flush()
            outcome = save_gap_scores(pupils, questions, request.form)
            db.session.commit()
            flash(f'{format_subject_name(subject)} GAP analysis saved for {school_class.name}.', 'success')
            for warning in outcome['warnings']:
                flash(warning, 'warning')
            return redirect(url_for('teacher.gap_analysis', subject=subject, academic_year=context['academic_year'], term=context['term']))
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'GAP analysis could not be saved: {exc}', 'danger')
            template = get_or_create_gap_template(school_class.year_group, subject, context['term'], context['academic_year'])

    gap_context = build_gap_page_context(pupils, template)
    return render_template('teacher/gap_analysis.html', **gap_context, **context)


@teacher_bp.route('/interventions', methods=['GET', 'POST'])
@login_required
@teacher_required
def interventions():
    school_class = get_primary_class_for_user(current_user)
    academic_year = request.values.get('academic_year', get_current_academic_year())
    term = request.values.get('term', get_current_term())
    subject = request.values.get('subject', 'maths')

    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/interventions.html', interventions=[], school_class=None, subjects=['maths', 'reading', 'spag'], academic_year=academic_year, academic_year_options=build_academic_year_options(academic_year), term=term, terms=TERMS, subject=subject, pupils=[], auto_reason=AUTO_REASON)

    setting = get_subject_setting(school_class.year_group, subject, term)
    sync_auto_interventions(school_class, subject, term, academic_year, setting.below_are_threshold_percent)

    if request.method == 'POST':
        action = request.form.get('action', 'update')
        try:
            if action == 'add_manual':
                pupil_id = int(request.form.get('pupil_id', '0'))
                note = request.form.get('note', '').strip() or None
                reason = request.form.get('reason', '').strip() or 'Teacher added manually'
                record = Intervention.query.filter_by(pupil_id=pupil_id, subject=subject, term=term, academic_year=academic_year, is_active=True).first()
                if not record:
                    record = Intervention(pupil_id=pupil_id, subject=subject, term=term, academic_year=academic_year, reason=reason, note=note, auto_flagged=False, is_active=True)
                else:
                    record.reason = reason
                    record.note = note
                    record.is_active = True
                db.session.add(record)
                flash('Manual intervention added.', 'success')
            else:
                for record in Intervention.query.join(Intervention.pupil).filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id).all():
                    record.note = request.form.get(f'note_{record.id}', '').strip() or None
                    record.is_active = request.form.get(f'active_{record.id}') == 'on'
                    db.session.add(record)
                flash('Interventions updated.', 'success')
            db.session.commit()
            return redirect(url_for('teacher.interventions', academic_year=academic_year, term=term, subject=subject))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Intervention changes could not be saved: {exc}', 'danger')

    interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id)
        .order_by(Intervention.is_active.desc(), Intervention.auto_flagged.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    return render_template(
        'teacher/interventions.html',
        school_class=school_class,
        interventions=interventions,
        pupils=pupils,
        subjects=['maths', 'reading', 'spag'],
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        term=term,
        terms=TERMS,
        subject=subject,
        auto_reason=AUTO_REASON,
    )


@teacher_bp.route('/sats', methods=['GET', 'POST'])
@login_required
@teacher_required
def sats_tracker():
    school_class = get_primary_class_for_user(current_user)
    academic_year = request.values.get('academic_year', get_current_academic_year())

    if not school_class or school_class.year_group != 6:
        flash('The SATs tracker is only available for the Year 6 teacher.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    if request.method == 'POST':
        try:
            _save_sats_rows(pupils, academic_year)
            db.session.commit()
            flash('SATs tracker saved.', 'success')
            return redirect(url_for('teacher.sats_tracker', academic_year=academic_year))
        except ValueError as exc:
            db.session.rollback()
            flash(f'SATs tracker could not be saved: {exc}', 'danger')

    rows = _build_sats_rows(pupils, academic_year)
    return render_template(
        'teacher/sats_tracker.html',
        school_class=school_class,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        rows=rows,
        sats_subjects=SATS_SUBJECTS,
        assessment_points=SATS_ASSESSMENT_POINTS,
        writing_band_choices=WRITING_BAND_CHOICES,
    )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value == '':
        return None
    return int(value)


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value == '':
        return None
    return float(value)


def _build_setting_payload(subject_key: str) -> dict:
    paper_1_max = _parse_int(request.form.get('paper_1_max'))
    paper_2_max = _parse_int(request.form.get('paper_2_max'))
    combined_max = _parse_int(request.form.get('combined_max'))
    below_threshold = _parse_float(request.form.get('below_are_threshold_percent'))
    exceeding_threshold = _parse_float(request.form.get('exceeding_threshold_percent'))

    if paper_1_max is None or paper_2_max is None or below_threshold is None or exceeding_threshold is None:
        raise AssessmentValidationError('Complete all settings fields before saving.')

    return {
        'paper_1_name': request.form.get('paper_1_name', '').strip(),
        'paper_1_max': paper_1_max,
        'paper_2_name': request.form.get('paper_2_name', '').strip(),
        'paper_2_max': paper_2_max,
        'combined_max': combined_max,
        'below_are_threshold_percent': below_threshold,
        'on_track_threshold_percent': below_threshold,
        'exceeding_threshold_percent': exceeding_threshold,
        'subject': subject_key,
    }


def _sort_subject_rows(rows: list[dict], sort_key: str) -> list[dict]:
    if sort_key == 'name_desc':
        return sorted(rows, key=lambda row: (row['pupil'].last_name.lower(), row['pupil'].first_name.lower()), reverse=True)
    if sort_key == 'percent_desc':
        return sorted(rows, key=lambda row: (row['combined_percent'] is None, -(row['combined_percent'] or 0), row['pupil'].last_name.lower()))
    if sort_key == 'percent_asc':
        return sorted(rows, key=lambda row: (row['combined_percent'] is None, row['combined_percent'] or 0, row['pupil'].last_name.lower()))
    if sort_key == 'band_asc':
        return sorted(rows, key=lambda row: ((row.get('band_display') or 'ZZZ'), row['pupil'].last_name.lower(), row['pupil'].first_name.lower()))
    return sorted(rows, key=lambda row: (row['pupil'].last_name.lower(), row['pupil'].first_name.lower(), row['pupil'].id))


def _filter_pupils(pupils: list[Pupil], search: str) -> list[Pupil]:
    if not search:
        return pupils
    search_value = search.lower()
    return [pupil for pupil in pupils if search_value in pupil.full_name.lower()]


def _base_subject_context(subject_key: str) -> dict:
    school_class = get_primary_class_for_user(current_user)
    current_year = get_current_academic_year()
    academic_year = request.values.get('academic_year', current_year)
    term = request.values.get('term', get_current_term())
    search = request.values.get('search', '').strip()
    sort = request.values.get('sort', 'name_asc')
    pupils = school_class.pupils.filter_by(is_active=True).all() if school_class else []
    pupils = _filter_pupils(pupils, search)
    return {
        'subject_key': subject_key,
        'page_title': SUBJECT_META[subject_key]['title'],
        'school_class': school_class,
        'current_year': current_year,
        'academic_year': academic_year,
        'term': term,
        'search': search,
        'sort': sort,
        'pupils': pupils,
        'academic_year_options': build_academic_year_options(academic_year),
        'sort_options': {key: label for key, label in SORT_OPTIONS.items() if key in {'name_asc', 'name_desc', 'percent_desc', 'percent_asc'}},
        'terms': TERMS,
    }


def _build_subject_rows(pupils: list[Pupil], existing_by_pupil: dict[int, SubjectResult]) -> list[dict]:
    rows = []
    for pupil in pupils:
        existing = existing_by_pupil.get(pupil.id)
        rows.append(
            {
                'pupil': pupil,
                'paper_1_score': '' if not existing or existing.paper_1_score is None else existing.paper_1_score,
                'paper_2_score': '' if not existing or existing.paper_2_score is None else existing.paper_2_score,
                'combined_score': existing.combined_score if existing else None,
                'combined_percent': existing.combined_percent if existing else None,
                'band_label': existing.band_label if existing else None,
                'notes': existing.notes if existing else '',
                'source': existing.source if existing else None,
            }
        )
    return rows


def render_subject_page(subject_key: str):
    context = _base_subject_context(subject_key)
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/subject_scores.html', rows=[], setting=None, active_interventions=[], **context)

    setting = get_subject_setting(school_class.year_group, subject_key, context['term'])

    if request.method == 'POST' and request.form.get('form_name') == 'settings':
        try:
            payload = _build_setting_payload(subject_key)
            payload.update({'year_group': school_class.year_group, 'term': context['term']})
            payload = validate_setting_payload(payload)
            update_assessment_setting(setting, payload)
            recalculated_count = recalculate_subject_results_for_scope(school_class.year_group, subject_key, context['term'], academic_year=context['academic_year'], class_id=school_class.id)
            db.session.commit()
            flash(
                f"{format_subject_name(subject_key)} settings saved for Year {school_class.year_group} {context['term'].title()}. Recalculated {recalculated_count} saved result(s).",
                'success',
            )
            return redirect(url_for(f'teacher.{subject_key}', academic_year=context['academic_year'], term=context['term'], search=context['search'], sort=context['sort']))
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'Settings could not be saved: {exc}', 'danger')
            setting = get_subject_setting(school_class.year_group, subject_key, context['term'])

    result_rows = (
        SubjectResult.query.join(SubjectResult.pupil)
        .filter(
            SubjectResult.subject == subject_key,
            SubjectResult.academic_year == context['academic_year'],
            SubjectResult.term == context['term'],
            SubjectResult.pupil.has(class_id=school_class.id),
        )
        .all()
    )
    existing_by_pupil = {result.pupil_id: result for result in result_rows}
    rows = []

    if request.method == 'POST' and request.form.get('form_name') == 'results':
        errors: list[str] = []
        for pupil in context['pupils']:
            paper_1_raw = request.form.get(f'paper_1_score_{pupil.id}', '')
            paper_2_raw = request.form.get(f'paper_2_score_{pupil.id}', '')
            notes = request.form.get(f'notes_{pupil.id}', '').strip()
            existing = existing_by_pupil.get(pupil.id)
            row = {
                'pupil': pupil,
                'paper_1_score': paper_1_raw.strip(),
                'paper_2_score': paper_2_raw.strip(),
                'notes': notes,
                'combined_score': existing.combined_score if existing else None,
                'combined_percent': existing.combined_percent if existing else None,
                'band_label': existing.band_label if existing else None,
                'source': existing.source if existing else None,
            }
            try:
                paper_1_score = _parse_int(paper_1_raw)
                paper_2_score = _parse_int(paper_2_raw)
                if paper_1_score is None and paper_2_score is None and not notes:
                    if existing:
                        db.session.delete(existing)
                    row.update({'combined_score': None, 'combined_percent': None, 'band_label': None, 'source': None})
                else:
                    computed = compute_subject_result_values(setting, paper_1_score, paper_2_score)
                    result = existing or SubjectResult(pupil_id=pupil.id, academic_year=context['academic_year'], term=context['term'], subject=subject_key)
                    result.paper_1_score = paper_1_score
                    result.paper_2_score = paper_2_score
                    result.combined_score = computed['combined_score']
                    result.combined_percent = computed['combined_percent']
                    result.band_label = computed['band_label']
                    result.source = 'manual'
                    result.notes = notes or None
                    db.session.add(result)
                    row.update({'paper_1_score': '' if paper_1_score is None else paper_1_score, 'paper_2_score': '' if paper_2_score is None else paper_2_score, 'combined_score': result.combined_score, 'combined_percent': result.combined_percent, 'band_label': result.band_label, 'source': result.source})
            except ValueError:
                errors.append(f'{pupil.full_name}: scores must be whole numbers.')
            except AssessmentValidationError as exc:
                errors.append(f'{pupil.full_name}: {exc}')
            rows.append(row)

        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, 'danger')
        else:
            sync_auto_interventions(school_class, subject_key, context['term'], context['academic_year'], setting.below_are_threshold_percent)
            db.session.commit()
            flash(f'{format_subject_name(subject_key)} results saved for {school_class.name}.', 'success')
            return redirect(url_for(f'teacher.{subject_key}', academic_year=context['academic_year'], term=context['term'], search=context['search'], sort=context['sort']))
    else:
        rows = _build_subject_rows(context['pupils'], existing_by_pupil)

    active_interventions = sync_auto_interventions(school_class, subject_key, context['term'], context['academic_year'], setting.below_are_threshold_percent)
    db.session.commit()
    rows = _sort_subject_rows(rows, context['sort'])
    return render_template('teacher/subject_scores.html', rows=rows, setting=setting, active_interventions=active_interventions, **context)


def render_writing_page():
    context = _base_subject_context('writing')
    context['sort_options'] = {key: label for key, label in SORT_OPTIONS.items() if key in {'name_asc', 'name_desc', 'band_asc'}}
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/writing_results.html', rows=[], writing_band_choices=WRITING_BAND_CHOICES, **context)

    existing_rows = (
        WritingResult.query.join(WritingResult.pupil)
        .filter(WritingResult.academic_year == context['academic_year'], WritingResult.term == context['term'], WritingResult.pupil.has(class_id=school_class.id))
        .all()
    )
    existing_by_pupil = {row.pupil_id: row for row in existing_rows}

    if request.method == 'POST':
        errors = []
        for pupil in context['pupils']:
            band = request.form.get(f'band_{pupil.id}', '').strip()
            notes = request.form.get(f'notes_{pupil.id}', '').strip()
            existing = existing_by_pupil.get(pupil.id)
            if not band and not notes:
                if existing:
                    db.session.delete(existing)
                continue
            if band and band not in {choice[0] for choice in WRITING_BAND_CHOICES}:
                errors.append(f'{pupil.full_name}: choose a valid writing band.')
                continue
            result = existing or WritingResult(pupil_id=pupil.id, academic_year=context['academic_year'], term=context['term'], band=band or 'working_towards')
            result.band = band or 'working_towards'
            result.notes = notes or None
            db.session.add(result)

        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, 'danger')
        else:
            db.session.commit()
            flash(f'Writing results saved for {school_class.name}.', 'success')
            return redirect(url_for('teacher.writing', academic_year=context['academic_year'], term=context['term'], search=context['search'], sort=context['sort']))

    rows = []
    for pupil in context['pupils']:
        existing = existing_by_pupil.get(pupil.id)
        rows.append({'pupil': pupil, 'band': existing.band if existing else '', 'notes': existing.notes if existing else ''})
    rows = _sort_subject_rows(rows, context['sort'])
    return render_template('teacher/writing_results.html', rows=rows, writing_band_choices=WRITING_BAND_CHOICES, **context)


def _save_sats_rows(pupils: list[Pupil], academic_year: str) -> None:
    for pupil in pupils:
        for subject in SATS_SUBJECTS:
            for point in SATS_ASSESSMENT_POINTS:
                raw = _parse_int(request.form.get(f'{subject}_raw_{point}_{pupil.id}', ''))
                scaled = _parse_int(request.form.get(f'{subject}_scaled_{point}_{pupil.id}', ''))
                existing = SatsResult.query.filter_by(pupil_id=pupil.id, subject=subject, assessment_point=point, academic_year=academic_year).first()
                if raw is None and scaled is None:
                    if existing:
                        db.session.delete(existing)
                    continue
                row = existing or SatsResult(pupil_id=pupil.id, subject=subject, assessment_point=point, academic_year=academic_year)
                row.raw_score = raw
                row.scaled_score = scaled
                db.session.add(row)

        for point in SATS_ASSESSMENT_POINTS:
            band = request.form.get(f'writing_band_{point}_{pupil.id}', '').strip()
            notes = request.form.get(f'writing_notes_{point}_{pupil.id}', '').strip()
            existing = SatsWritingResult.query.filter_by(pupil_id=pupil.id, assessment_point=point, academic_year=academic_year).first()
            if not band and not notes:
                if existing:
                    db.session.delete(existing)
                continue
            if band and band not in {choice[0] for choice in WRITING_BAND_CHOICES}:
                raise ValueError(f'{pupil.full_name} writing point {point}: invalid band.')
            row = existing or SatsWritingResult(pupil_id=pupil.id, assessment_point=point, academic_year=academic_year)
            row.band = band or None
            row.notes = notes or None
            db.session.add(row)

    for pupil in pupils:
        for subject in SATS_SUBJECTS:
            subject_rows = SatsResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, subject=subject).order_by(SatsResult.assessment_point).all()
            latest_point = max((row.assessment_point for row in subject_rows if row.scaled_score is not None), default=None)
            for row in subject_rows:
                row.is_most_recent = row.assessment_point == latest_point if latest_point is not None else False
                db.session.add(row)


def _build_sats_rows(pupils: list[Pupil], academic_year: str) -> list[dict]:
    rows = []
    for pupil in pupils:
        subject_map = {}
        for subject in SATS_SUBJECTS:
            subject_rows = SatsResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, subject=subject).all()
            subject_map[subject] = get_sats_subject_summary(subject_rows)
        writing_rows = SatsWritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year).all()
        rows.append({'pupil': pupil, 'subjects': subject_map, 'writing': get_sats_writing_summary(writing_rows)})
    return rows
