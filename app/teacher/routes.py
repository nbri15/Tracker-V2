"""Teacher assessment entry routes."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models import GapQuestion, Intervention, Pupil, SubjectResult, WritingResult
from app.services import (
    AUTO_REASON,
    SATS_ASSESSMENT_POINTS,
    SATS_COLUMN_SUBJECTS,
    SATS_SCORE_TYPES,
    SATS_SUBJECTS,
    RECEPTION_AREAS,
    RECEPTION_STATUS_CHOICES,
    RECEPTION_TRACKING_POINTS,
    SATS_TRACKER_MODES,
    TERMS,
    WRITING_BAND_CHOICES,
    AssessmentValidationError,
    apply_admin_pupil_filters,
    build_academic_year_options,
    build_reception_overview,
    build_reception_summary,
    build_reception_tracker_rows,
    build_admin_pupil_filter_state,
    build_gap_page_context,
    build_phonics_tracker_rows,
    build_sort_indicator,
    build_table_sort_state,
    build_sats_tracker_rows,
    compute_subject_result_values,
    format_subject_name,
    get_current_academic_year,
    get_current_term,
    get_gender_filter_options,
    get_next_sort_direction,
    get_or_create_gap_template,
    get_reception_class,
    get_result_outcome_theme,
    get_sats_columns,
    get_sats_exam_tabs,
    get_subject_setting,
    get_tracking_point_key,
    get_tracker_mode,
    get_tracker_mode_label,
    get_writing_band_label,
    is_ks1_year_group,
    get_writing_outcome_theme,
    parse_question_columns,
    recalculate_subject_results_for_scope,
    save_reception_tracker_entries,
    save_gap_scores,
    save_phonics_columns,
    save_phonics_scores,
    save_sats_column,
    save_sats_tab,
    save_sats_tracker_results,
    set_tracker_mode,
    sync_auto_interventions,
    toggle_sats_column,
    toggle_sats_tab,
    update_assessment_setting,
    validate_setting_payload,
    add_phonics_column,
    ensure_phonics_columns,
    ReceptionTrackerValidationError,
    SatsColumnValidationError,
    sort_subject_result_rows,
    sort_writing_result_rows,
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


@teacher_bp.route('/phonics', methods=['GET', 'POST'])
@login_required
@teacher_required
def phonics():
    school_class = get_primary_class_for_user(current_user)
    academic_year = request.values.get('academic_year', get_current_academic_year())
    filters = build_admin_pupil_filter_state(request.values)

    if not school_class or not is_ks1_year_group(school_class.year_group):
        flash('The phonics tracker is only available for Year 1 and Year 2 classes.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    pupils = apply_admin_pupil_filters(school_class.pupils.filter_by(is_active=True), filters).order_by(Pupil.last_name, Pupil.first_name).all()
    columns = ensure_phonics_columns(school_class.year_group)

    if request.method == 'POST':
        action = request.form.get('action', 'save_scores')
        try:
            if action == 'save_columns':
                columns = save_phonics_columns(school_class.year_group, request.form)
                flash('Phonics test columns updated.', 'success')
            elif action == 'add_column':
                column = add_phonics_column(school_class.year_group, request.form)
                flash(f'Added phonics column {column.name}.', 'success')
            else:
                save_phonics_scores(pupils, columns, academic_year, request.form)
                flash('Phonics scores saved.', 'success')
            db.session.commit()
            return redirect(url_for('teacher.phonics', academic_year=academic_year, search=filters['search'], gender=filters['gender'], pupil_premium=filters['pupil_premium'], laps=filters['laps'], service_child=filters['service_child']))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Phonics changes could not be saved: {exc}', 'danger')
            columns = ensure_phonics_columns(school_class.year_group)

    rows = build_phonics_tracker_rows(pupils, columns, academic_year)
    return render_template(
        'teacher/phonics_tracker.html',
        school_class=school_class,
        pupils=pupils,
        rows=rows,
        columns=columns,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        gender_options=get_gender_filter_options(class_id=school_class.id),
    )


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
        return render_template('teacher/gap_analysis.html', rows=[], questions=[], template=None, max_total=0, papers=[], active_paper='paper_1', setting=None, **context)

    template = get_or_create_gap_template(school_class.year_group, subject, context['term'], context['academic_year'])
    pupils = context['pupils']
    setting = get_subject_setting(school_class.year_group, subject, context['term'])
    paper_tabs = [
        {'key': 'paper_1', 'label': setting.paper_1_name or 'Paper 1'},
        {'key': 'paper_2', 'label': setting.paper_2_name or 'Paper 2'},
    ]
    active_paper = request.values.get('paper', paper_tabs[0]['key'])
    valid_paper_keys = {paper['key'] for paper in paper_tabs}
    if active_paper not in valid_paper_keys:
        active_paper = paper_tabs[0]['key']

    if request.method == 'POST':
        try:
            action = request.form.get('action', 'save_gap')
            active_paper = request.form.get('active_paper', active_paper)
            if active_paper not in valid_paper_keys:
                active_paper = paper_tabs[0]['key']
            if action == 'add_question':
                label = request.form.get('new_question_label', '').strip()
                max_raw = request.form.get('new_question_max', '').strip()
                question_type = request.form.get('new_question_type', '').strip() or None
                if not label:
                    raise AssessmentValidationError('Enter a question label before adding a new question.')
                try:
                    max_score = int(max_raw or '0')
                except ValueError as exc:
                    raise AssessmentValidationError('New question max score must be a whole number.') from exc
                if max_score < 0:
                    raise AssessmentValidationError('New question max score cannot be negative.')
                next_order = len(template.questions)
                question = GapQuestion(
                    template=template,
                    paper_key=active_paper,
                    question_label=label,
                    question_type=question_type,
                    max_score=max_score,
                    display_order=next_order,
                )
                db.session.add(question)
                db.session.commit()
                flash(f'Added question {label} to {dict((item["key"], item["label"]) for item in paper_tabs)[active_paper]}.', 'success')
            else:
                template.paper_name = request.form.get('paper_name', '').strip() or None
                questions = parse_question_columns(request.form, template)
                db.session.flush()
                outcome = save_gap_scores(pupils, questions, request.form)
                db.session.commit()
                flash(f'{format_subject_name(subject)} GAP analysis saved for {school_class.name}.', 'success')
                for warning in outcome['warnings']:
                    flash(warning, 'warning')
            return redirect(url_for('teacher.gap_analysis', subject=subject, academic_year=context['academic_year'], term=context['term'], paper=active_paper))
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'GAP analysis could not be saved: {exc}', 'danger')
            template = get_or_create_gap_template(school_class.year_group, subject, context['term'], context['academic_year'])

    gap_context = build_gap_page_context(pupils, template)
    papers_by_key = {paper['key']: paper for paper in gap_context.get('papers', [])}
    gap_context['papers'] = [
        {
            **paper,
            **papers_by_key.get(paper['key'], {'questions': [], 'max_total': 0, 'question_averages': []}),
        }
        for paper in paper_tabs
    ]
    gap_context['active_paper'] = active_paper
    return render_template('teacher/gap_analysis.html', setting=setting, **gap_context, **context)


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
                for record in Intervention.query.join(Intervention.pupil).filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id, Pupil.is_active.is_(True)).all():
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
        .filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id, Pupil.is_active.is_(True))
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
    selected_tab_id_raw = request.values.get('exam_tab_id', '').strip()

    if not school_class or school_class.year_group != 6:
        flash('The SATs tracker is only available for the Year 6 teacher.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    tracker_mode = get_tracker_mode(6)
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()

    if request.method == 'POST':
        action = request.form.get('action', 'save_results')
        if action == 'add_pupil':
            return _handle_quick_add_pupil(
                school_class,
                redirect_endpoint='teacher.sats_tracker',
                context={
                    'academic_year': academic_year,
                    'term': get_current_term(),
                    'filters': build_admin_pupil_filter_state({}),
                    'sort_state': {'column': 'name', 'direction': 'asc'},
                },
                exam_tab_id=selected_tab_id_raw or None,
            )
        try:
            if action == 'update_mode':
                set_tracker_mode(6, request.form.get('tracker_mode', 'sats'))
                flash(f'Year 6 tracker mode changed to {get_tracker_mode_label(6)}.', 'success')
            elif action == 'save_tab':
                tab_id = int(request.form.get('tab_id', '0')) or None
                tab = save_sats_tab({
                    'year_group': 6,
                    'name': request.form.get('tab_name', ''),
                    'display_order': request.form.get('tab_display_order', '1'),
                    'is_active': request.form.get('tab_is_active') == 'on',
                }, tab_id=tab_id)
                selected_tab_id_raw = str(tab.id)
                flash('SATs exam tab saved.', 'success')
            elif action == 'toggle_tab':
                tab = toggle_sats_tab(int(request.form.get('tab_id', '0')))
                selected_tab_id_raw = str(tab.id)
                flash(f"{tab.name} is now {'shown' if tab.is_active else 'hidden'}.", 'success')
            elif action == 'save_column':
                column_id = int(request.form.get('column_id', '0')) or None
                exam_tab_id = int(request.form.get('exam_tab_id', '0') or selected_tab_id_raw or '0')
                save_sats_column(6, {
                    'name': request.form.get('name', ''),
                    'subject': request.form.get('subject', ''),
                    'score_type': request.form.get('score_type', 'paper'),
                    'max_marks': request.form.get('max_marks', '0'),
                    'pass_percentage': request.form.get('pass_percentage', '0'),
                    'display_order': request.form.get('display_order', '1'),
                    'is_active': request.form.get('is_active') == 'on',
                }, exam_tab_id=exam_tab_id, column_id=column_id)
                selected_tab_id_raw = str(exam_tab_id)
                flash('SATs column saved.', 'success')
            elif action == 'toggle_column':
                column = toggle_sats_column(int(request.form.get('column_id', '0')))
                selected_tab_id_raw = str(column.exam_tab_id)
                state = 'shown' if column.is_active else 'hidden'
                flash(f'{column.name} is now {state}.', 'success')
            else:
                exam_tab_id = int(request.form.get('exam_tab_id', '0') or selected_tab_id_raw or '0')
                columns = get_sats_columns(6, exam_tab_id=exam_tab_id, active_only=True)
                save_sats_tracker_results(pupils, academic_year, columns, request.form)
                selected_tab_id_raw = str(exam_tab_id)
                flash('SATs tracker saved.', 'success')
            db.session.commit()
            return redirect(url_for('teacher.sats_tracker', academic_year=academic_year, exam_tab_id=selected_tab_id_raw or None))
        except (ValueError, SatsColumnValidationError) as exc:
            db.session.rollback()
            flash(f'SATs changes could not be saved: {exc}', 'danger')

    selected_tab_id = int(selected_tab_id_raw) if selected_tab_id_raw else None
    columns, rows, overview = build_sats_tracker_rows(pupils, academic_year, 6, exam_tab_id=selected_tab_id, active_only=True)
    selected_tab = overview.pop('_selected_tab', None)
    tabs = overview.pop('_tabs', get_sats_exam_tabs(6, include_inactive=True))
    return render_template(
        'teacher/sats_tracker.html',
        school_class=school_class,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        tracker_mode=tracker_mode,
        tracker_mode_label=get_tracker_mode_label(6),
        tracker_mode_options=SATS_TRACKER_MODES,
        columns=columns,
        all_columns=get_sats_columns(6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=False),
        tabs=tabs,
        selected_tab=selected_tab,
        rows=rows,
        overview=overview,
        sats_subject_choices=SATS_COLUMN_SUBJECTS,
        sats_score_type_choices=SATS_SCORE_TYPES,
    )


@teacher_bp.route('/reception', methods=['GET', 'POST'])
@login_required
@teacher_required
def reception_tracker():
    school_class = get_primary_class_for_user(current_user)
    reception_class = get_reception_class()
    if not reception_class or not school_class or school_class.id != reception_class.id:
        flash('The Reception tracker is only available for the Reception teacher.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    academic_year = request.values.get('academic_year', get_current_academic_year())
    tracking_point = get_tracking_point_key(request.values.get('tracking_point'))
    view = (request.values.get('view', 'tracker') or 'tracker').strip().lower()
    if view not in {'tracker', 'overview'}:
        view = 'tracker'
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()

    if request.method == 'POST':
        tracking_point = get_tracking_point_key(request.form.get('tracking_point'))
        try:
            save_reception_tracker_entries(pupils, academic_year, tracking_point, request.form)
            db.session.commit()
            flash(f'Reception tracker saved for {dict(RECEPTION_TRACKING_POINTS)[tracking_point]}.', 'success')
            return redirect(url_for('teacher.reception_tracker', academic_year=academic_year, tracking_point=tracking_point, view=view))
        except ReceptionTrackerValidationError as exc:
            db.session.rollback()
            flash(f'Reception tracker could not be saved: {exc}', 'danger')

    rows = build_reception_tracker_rows(pupils, academic_year, tracking_point)
    summary = build_reception_summary(rows)
    overview = build_reception_overview(rows)
    return render_template(
        'teacher/reception_tracker.html',
        school_class=school_class,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        tracking_points=RECEPTION_TRACKING_POINTS,
        selected_tracking_point=tracking_point,
        areas=RECEPTION_AREAS,
        status_choices=RECEPTION_STATUS_CHOICES,
        rows=rows,
        summary=summary,
        overview=overview,
        selected_view=view,
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


SUBJECT_SORTABLE_COLUMNS = {'name', 'paper_1_score', 'paper_2_score', 'combined_score', 'combined_percent', 'band_label'}
WRITING_SORTABLE_COLUMNS = {'name', 'band_label', 'notes'}


def _table_header_state(sort_state: dict, allowed_columns: set[str]) -> dict:
    return {
        column: {
            'indicator': build_sort_indicator(column, sort_state),
            'next_direction': get_next_sort_direction(column, sort_state),
            'active': sort_state['column'] == column,
        }
        for column in allowed_columns
    }


def _quick_add_redirect(endpoint: str, context: dict, **extra_params):
    params = {
        'academic_year': context['academic_year'],
        'term': context['term'],
        'search': context['filters']['search'],
        'gender': context['filters']['gender'],
        'pupil_premium': context['filters']['pupil_premium'],
        'laps': context['filters']['laps'],
        'service_child': context['filters']['service_child'],
        'sort': context['sort_state']['column'],
        'direction': context['sort_state']['direction'],
    }
    params.update(extra_params)
    return redirect(url_for(endpoint, **params))


def _handle_quick_add_pupil(school_class, *, redirect_endpoint: str, context: dict, **extra_params):
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return _quick_add_redirect(redirect_endpoint, context, **extra_params)

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    gender = request.form.get('gender', '').strip() or 'Unknown'
    if not first_name or not last_name:
        flash('Enter both first and last name before adding a pupil.', 'danger')
        return _quick_add_redirect(redirect_endpoint, context, show_add_pupil='1', **extra_params)

    duplicate = Pupil.query.filter(
        Pupil.class_id == school_class.id,
        func.lower(Pupil.first_name) == first_name.lower(),
        func.lower(Pupil.last_name) == last_name.lower(),
    ).first()
    if duplicate:
        flash(
            f'{duplicate.full_name} already exists in {school_class.name}. Check names before creating a duplicate record.',
            'warning',
        )
        return _quick_add_redirect(redirect_endpoint, context, show_add_pupil='1', **extra_params)

    pupil = Pupil(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        pupil_premium=request.form.get('pupil_premium') == 'on',
        laps=request.form.get('laps') == 'on',
        service_child=request.form.get('service_child') == 'on',
        class_id=school_class.id,
        is_active=True,
    )
    db.session.add(pupil)
    db.session.commit()
    flash(f'Added {pupil.full_name} to {school_class.name}.', 'success')
    return _quick_add_redirect(redirect_endpoint, context, **extra_params)


def _base_subject_context(subject_key: str) -> dict:
    school_class = get_primary_class_for_user(current_user)
    current_year = get_current_academic_year()
    academic_year = request.values.get('academic_year', current_year)
    term = request.values.get('term', get_current_term())
    filters = build_admin_pupil_filter_state(request.values)
    sort_state = build_table_sort_state(
        request.values,
        allowed_columns=WRITING_SORTABLE_COLUMNS if subject_key == 'writing' else SUBJECT_SORTABLE_COLUMNS,
        default_column='name',
    )
    pupils = []
    if school_class:
        pupils = apply_admin_pupil_filters(school_class.pupils.filter_by(is_active=True), filters).all()
    return {
        'subject_key': subject_key,
        'page_title': SUBJECT_META[subject_key]['title'],
        'school_class': school_class,
        'current_year': current_year,
        'academic_year': academic_year,
        'term': term,
        'filters': filters,
        'sort_state': sort_state,
        'pupils': pupils,
        'academic_year_options': build_academic_year_options(academic_year),
        'gender_options': get_gender_filter_options(class_id=school_class.id) if school_class else [],
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
                'outcome_theme': get_result_outcome_theme(existing.band_label if existing else None),
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
            return redirect(
                url_for(
                    f'teacher.{subject_key}',
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['filters']['search'],
                    gender=context['filters']['gender'],
                    pupil_premium=context['filters']['pupil_premium'],
                    laps=context['filters']['laps'],
                    service_child=context['filters']['service_child'],
                    sort=context['sort_state']['column'],
                    direction=context['sort_state']['direction'],
                )
            )
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'Settings could not be saved: {exc}', 'danger')
            setting = get_subject_setting(school_class.year_group, subject_key, context['term'])
    elif request.method == 'POST' and request.form.get('form_name') == 'add_pupil':
        return _handle_quick_add_pupil(
            school_class,
            redirect_endpoint=f'teacher.{subject_key}',
            context=context,
        )

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
                'outcome_theme': get_result_outcome_theme(existing.band_label if existing else None),
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
                    row.update({
                        'paper_1_score': '' if paper_1_score is None else paper_1_score,
                        'paper_2_score': '' if paper_2_score is None else paper_2_score,
                        'combined_score': result.combined_score,
                        'combined_percent': result.combined_percent,
                        'band_label': result.band_label,
                        'source': result.source,
                        'outcome_theme': get_result_outcome_theme(result.band_label),
                    })
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
            return redirect(
                url_for(
                    f'teacher.{subject_key}',
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['filters']['search'],
                    gender=context['filters']['gender'],
                    pupil_premium=context['filters']['pupil_premium'],
                    laps=context['filters']['laps'],
                    service_child=context['filters']['service_child'],
                    sort=context['sort_state']['column'],
                    direction=context['sort_state']['direction'],
                )
            )
    else:
        rows = _build_subject_rows(context['pupils'], existing_by_pupil)

    active_interventions = sync_auto_interventions(school_class, subject_key, context['term'], context['academic_year'], setting.below_are_threshold_percent)
    db.session.commit()
    rows = sort_subject_result_rows(rows, context['sort_state']['column'], context['sort_state']['direction'])
    return render_template(
        'teacher/subject_scores.html',
        rows=rows,
        setting=setting,
        active_interventions=active_interventions,
        header_state=_table_header_state(context['sort_state'], SUBJECT_SORTABLE_COLUMNS),
        **context,
    )


def render_writing_page():
    context = _base_subject_context('writing')
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
        if request.form.get('form_name') == 'add_pupil':
            return _handle_quick_add_pupil(
                school_class,
                redirect_endpoint='teacher.writing',
                context=context,
            )
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
            result.source = 'manual'
            db.session.add(result)

        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, 'danger')
        else:
            db.session.commit()
            flash(f'Writing results saved for {school_class.name}.', 'success')
            return redirect(
                url_for(
                    'teacher.writing',
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['filters']['search'],
                    gender=context['filters']['gender'],
                    pupil_premium=context['filters']['pupil_premium'],
                    laps=context['filters']['laps'],
                    service_child=context['filters']['service_child'],
                    sort=context['sort_state']['column'],
                    direction=context['sort_state']['direction'],
                )
            )

    rows = []
    for pupil in context['pupils']:
        existing = existing_by_pupil.get(pupil.id)
        rows.append({
            'pupil': pupil,
            'band': existing.band if existing else '',
            'band_label': get_writing_band_label(existing.band) if existing else '—',
            'notes': existing.notes if existing else '',
            'outcome_theme': get_writing_outcome_theme(existing.band if existing else None),
        })
    rows = sort_writing_result_rows(rows, context['sort_state']['column'], context['sort_state']['direction'])
    return render_template(
        'teacher/writing_results.html',
        rows=rows,
        writing_band_choices=WRITING_BAND_CHOICES,
        header_state=_table_header_state(context['sort_state'], WRITING_SORTABLE_COLUMNS),
        **context,
    )
