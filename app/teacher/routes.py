"""Teacher assessment entry routes."""

from __future__ import annotations

from datetime import date, datetime, timezone

from flask import current_app, flash, make_response, redirect, render_template, request, url_for
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
    FOUNDATION_HALF_TERMS,
    FOUNDATION_JUDGEMENTS,
    FOUNDATION_SUBJECTS,
    FOUNDATION_JUDGEMENT_THEMES,
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
    build_foundation_summary,
    build_foundation_tracker_rows,
    build_gap_page_context,
    build_phonics_tracker_rows,
    build_sort_indicator,
    build_table_sort_state,
    build_sats_tracker_rows,
    compute_subject_result_values,
    format_subject_name,
    format_progress_delta,
    previous_term,
    progress_theme,
    get_selected_current_academic_year,
    get_selected_academic_year,
    get_current_term,
    get_class_pupil_query,
    get_foundation_half_term,
    get_gender_filter_options,
    get_latest_previous_assessment,
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
    resolve_subject_band_label,
    save_reception_tracker_entries,
    save_foundation_results,
    save_gap_scores,
    sync_gap_totals_to_subject_results,
    save_phonics_columns,
    save_phonics_scores,
    sort_phonics_tracker_rows,
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
    add_times_tables_column,
    ensure_phonics_columns,
    ensure_times_tables_columns,
    ReceptionTrackerValidationError,
    SatsColumnValidationError,
    sort_subject_result_rows,
    sort_writing_result_rows,
    build_times_tables_tracker_rows,
    is_times_tables_year_group,
    save_times_tables_columns,
    save_times_tables_scores,
    sort_times_tables_tracker_rows,
    FoundationValidationError,
)
from app.utils import get_primary_class_for_user, get_year_group_class_for_user, teacher_required
from app.services.pupil_quick_add import create_quick_add_pupil

from . import teacher_bp


SUBJECT_META = {
    'maths': {'title': 'Maths'},
    'reading': {'title': 'Reading'},
    'spag': {'title': 'SPaG'},
    'writing': {'title': 'Writing'},
}
JOIN_YEAR_GROUP_CHOICES = [('', 'Unknown'), (0, 'Reception')] + [(year, f'Year {year}') for year in range(1, 7)]


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
    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    filters = build_admin_pupil_filter_state(request.values)

    if not school_class or not is_ks1_year_group(school_class.year_group):
        flash('The phonics tracker is only available for Year 1 and Year 2 classes.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    pupils = apply_admin_pupil_filters(get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)), filters).order_by(Pupil.last_name, Pupil.first_name).all()
    columns = ensure_phonics_columns(school_class.year_group, school_class.school_id)
    active_columns = [column for column in columns if column.is_active]
    sortable_columns = {'name', *(f'column_{column.id}' for column in active_columns)}
    sort_state = build_table_sort_state(request.values, allowed_columns=sortable_columns, default_column='name')
    header_state = {
        column: {
            'indicator': build_sort_indicator(column, sort_state),
            'next_direction': get_next_sort_direction(column, sort_state),
            'active': sort_state['column'] == column,
        }
        for column in sortable_columns
    }

    if request.method == 'POST':
        action = request.form.get('action', 'save_scores')
        try:
            if action == 'save_columns':
                columns = save_phonics_columns(school_class.year_group, school_class.school_id, request.form)
                flash('Phonics test columns updated.', 'success')
            elif action == 'add_column':
                column = add_phonics_column(school_class.year_group, school_class.school_id, request.form)
                flash(f'Added phonics column {column.name}.', 'success')
            else:
                save_phonics_scores(pupils, columns, academic_year, school_class.school_id, request.form)
                flash('Phonics scores saved.', 'success')
            db.session.commit()
            return redirect(url_for('teacher.phonics', academic_year=academic_year, search=filters['search'], gender=filters['gender'], pupil_premium=filters['pupil_premium'], laps=filters['laps'], service_child=filters['service_child'], sort=sort_state['column'], direction=sort_state['direction']))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Phonics changes could not be saved: {exc}', 'danger')
            columns = ensure_phonics_columns(school_class.year_group, school_class.school_id)

    rows = build_phonics_tracker_rows(pupils, columns, academic_year, school_class.school_id)
    rows = sort_phonics_tracker_rows(rows, sort_state['column'], sort_state['direction'])
    return render_template(
        'teacher/phonics_tracker.html',
        school_class=school_class,
        pupils=pupils,
        rows=rows,
        columns=columns,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        sort_state=sort_state,
        header_state=header_state,
        gender_options=get_gender_filter_options(class_id=school_class.id),
    )


@teacher_bp.route('/times_tables', methods=['GET', 'POST'])
@login_required
@teacher_required
def times_tables():
    school_class = get_primary_class_for_user(current_user)
    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    filters = build_admin_pupil_filter_state(request.values)

    if not school_class or not is_times_tables_year_group(school_class.year_group):
        flash('The times tables tracker is only available for Year 4 classes.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    pupils = apply_admin_pupil_filters(get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)), filters).order_by(Pupil.last_name, Pupil.first_name).all()
    columns = ensure_times_tables_columns(school_class.year_group)
    active_columns = [column for column in columns if column.is_active]
    sortable_columns = {'name', *(f'column_{column.id}' for column in active_columns)}
    sort_state = build_table_sort_state(request.values, allowed_columns=sortable_columns, default_column='name')
    header_state = {
        column: {
            'indicator': build_sort_indicator(column, sort_state),
            'next_direction': get_next_sort_direction(column, sort_state),
            'active': sort_state['column'] == column,
        }
        for column in sortable_columns
    }

    if request.method == 'POST':
        action = request.form.get('action', 'save_scores')
        try:
            if action == 'save_columns':
                columns = save_times_tables_columns(school_class.year_group, request.form)
                flash('Times tables test columns updated.', 'success')
            elif action == 'add_column':
                column = add_times_tables_column(school_class.year_group, request.form)
                flash(f'Added times tables column {column.name}.', 'success')
            else:
                save_times_tables_scores(pupils, columns, academic_year, request.form)
                flash('Times tables scores saved.', 'success')
            db.session.commit()
            return redirect(url_for('teacher.times_tables', academic_year=academic_year, search=filters['search'], gender=filters['gender'], pupil_premium=filters['pupil_premium'], laps=filters['laps'], service_child=filters['service_child'], sort=sort_state['column'], direction=sort_state['direction']))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Times tables changes could not be saved: {exc}', 'danger')
            columns = ensure_times_tables_columns(school_class.year_group)

    rows = build_times_tables_tracker_rows(pupils, columns, academic_year)
    rows = sort_times_tables_tracker_rows(rows, sort_state['column'], sort_state['direction'])
    return render_template(
        'teacher/times_tables_tracker.html',
        school_class=school_class,
        pupils=pupils,
        rows=rows,
        columns=columns,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        sort_state=sort_state,
        header_state=header_state,
        gender_options=get_gender_filter_options(class_id=school_class.id),
    )


@teacher_bp.route('/foundation', methods=['GET', 'POST'])
@login_required
@teacher_required
def foundation():
    school_class = get_primary_class_for_user(current_user)
    if not school_class:
        flash('No active class is assigned to your account.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    half_term = get_foundation_half_term(request.values.get('half_term'))
    filters = build_admin_pupil_filter_state(request.values)
    pupils = apply_admin_pupil_filters(get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)), filters).order_by(Pupil.last_name, Pupil.first_name).all()

    if request.method == 'POST':
        half_term = get_foundation_half_term(request.form.get('half_term'))
        try:
            save_foundation_results(pupils, academic_year, half_term, request.form, user_id=current_user.id)
            db.session.commit()
            flash('Foundation judgements saved.', 'success')
            return redirect(
                url_for(
                    'teacher.foundation',
                    academic_year=academic_year,
                    half_term=half_term,
                    search=filters['search'],
                    gender=filters['gender'],
                    pupil_premium=filters['pupil_premium'],
                    laps=filters['laps'],
                    service_child=filters['service_child'],
                )
            )
        except FoundationValidationError as exc:
            db.session.rollback()
            flash(f'Foundation changes could not be saved: {exc}', 'danger')

    rows = build_foundation_tracker_rows(pupils, academic_year, half_term)
    summary = build_foundation_summary(rows)
    return render_template(
        'teacher/foundation_tracker.html',
        school_class=school_class,
        pupils=pupils,
        rows=rows,
        summary=summary,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        half_terms=FOUNDATION_HALF_TERMS,
        selected_half_term=half_term,
        subjects=FOUNDATION_SUBJECTS,
        judgement_choices=FOUNDATION_JUDGEMENTS,
        judgement_themes=FOUNDATION_JUDGEMENT_THEMES,
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
    if template.school_id != school_class.school_id:
        template.school_id = school_class.school_id
        db.session.add(template)
        db.session.flush()
    pupils = context['pupils']
    setting = get_subject_setting(school_class.year_group, subject, context['term'], context['academic_year'], school_id=school_class.school_id)
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
                    school_id=school_class.school_id,
                )
                db.session.add(question)
                db.session.commit()
                flash(f'Added question {label} to {dict((item["key"], item["label"]) for item in paper_tabs)[active_paper]}.', 'success')
            elif action == 'sync_results':
                questions = list(template.questions)
                outcome = {'warnings': sync_gap_totals_to_subject_results(
                    pupils,
                    questions,
                    school_id=school_class.school_id,
                    assessment_year_group=school_class.year_group,
                )}
                db.session.commit()
                flash(f'QLA saved and synced to {context["academic_year"]} results table.', 'success')
                for warning in outcome['warnings']:
                    flash(warning, 'warning')
            else:
                template.paper_name = request.form.get('paper_name', '').strip() or None
                questions = parse_question_columns(request.form, template)
                db.session.flush()
                outcome = save_gap_scores(
                    pupils,
                    questions,
                    request.form,
                    school_id=school_class.school_id,
                    assessment_year_group=school_class.year_group,
                )
                db.session.commit()
                flash(f'QLA saved and synced to {context["academic_year"]} results table.', 'success')
                for warning in outcome['warnings']:
                    flash(warning, 'warning')
            return redirect(url_for('teacher.gap_analysis', subject=subject, year=context['selected_year'].id, academic_year=context['academic_year'], term=context['term'], paper=active_paper))
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
    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    term = request.values.get('term', get_current_term())
    subject = request.values.get('subject', 'maths')

    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/interventions.html', interventions=[], school_class=None, subjects=['maths', 'reading', 'spag'], academic_year=academic_year, academic_year_options=build_academic_year_options(academic_year), term=term, terms=TERMS, subject=subject, pupils=[], auto_reason=AUTO_REASON)

    # Automatic suggestions are refreshed by explicit result/configuration saves.
    # Merely viewing interventions must not alter historical records.

    if request.method == 'POST':
        action = request.form.get('action', 'update')
        try:
            if action == 'add_manual':
                pupil_id = int(request.form.get('pupil_id', '0'))
                pupil = get_class_pupil_query(school_class, academic_year).filter(Pupil.id == pupil_id, Pupil.is_active.is_(True), Pupil.school_id == school_class.school_id).first()
                if not pupil:
                    raise ValueError('Choose a pupil from your assigned class.')
                note = request.form.get('note', '').strip() or None
                reason = request.form.get('reason', '').strip() or 'Teacher added manually'
                record = Intervention.query.join(Intervention.pupil).filter(Intervention.pupil_id == pupil_id, Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Intervention.is_active.is_(True), Pupil.class_id == school_class.id, Pupil.school_id == school_class.school_id).first()
                if not record:
                    record = Intervention(
                        pupil_id=pupil_id,
                        school_id=school_class.school_id,
                        subject=subject,
                        term=term,
                        academic_year=academic_year,
                        reason=reason,
                        note=note,
                        auto_flagged=False,
                        is_active=True,
                        is_demo=school_class.is_demo,
                    )
                else:
                    record.reason = reason
                    record.note = note
                    record.is_active = True
                db.session.add(record)
                flash('Manual intervention added.', 'success')
            else:
                for record in Intervention.query.join(Intervention.pupil).filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id, Pupil.school_id == school_class.school_id, Pupil.is_active.is_(True)).all():
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
        .filter(Intervention.subject == subject, Intervention.term == term, Intervention.academic_year == academic_year, Pupil.class_id == school_class.id, Pupil.school_id == school_class.school_id, Pupil.is_active.is_(True))
        .order_by(Intervention.is_active.desc(), Intervention.auto_flagged.desc(), Pupil.last_name, Pupil.first_name)
        .all()
    )
    pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True), Pupil.school_id == school_class.school_id).order_by(Pupil.last_name, Pupil.first_name).all()
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




@teacher_bp.route('/api/interventions/quick-save', methods=['POST'])
@login_required
@teacher_required
def interventions_quick_save():
    data = request.get_json(silent=True) or {}
    school_class = get_primary_class_for_user(current_user)
    if not school_class:
        return {'ok': False}, 400
    try:
        record_id = int(data.get('record_id') or 0)
    except (TypeError, ValueError):
        return {'ok': False}, 400
    record = Intervention.query.join(Intervention.pupil).filter(Intervention.id == record_id, Pupil.class_id == school_class.id, Pupil.school_id == school_class.school_id).first()
    if not record:
        return {'ok': False}, 404
    field = (data.get('field') or '').strip()
    if field not in {'note', 'is_active'}:
        return {'ok': False}, 400
    value = data.get('value')
    if field == 'note':
        record.note = (value or '').strip() or None
    else:
        record.is_active = bool(value)
    db.session.add(record); db.session.commit()
    return {'ok': True}

@teacher_bp.route('/sats', methods=['GET', 'POST'])
@login_required
@teacher_required
def sats_tracker():
    return redirect(url_for('dashboards.sats_simple'))

# legacy disabled
def _legacy_sats_tracker_disabled():
    school_class = get_year_group_class_for_user(current_user, 6)
    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    selected_tab_id_raw = request.values.get('exam_tab_id', '').strip()

    if not school_class:
        flash('Year 6 SATs tracker is only available for Year 6.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))

    tracker_mode = get_tracker_mode(6)
    pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True), Pupil.school_id == school_class.school_id).order_by(Pupil.last_name, Pupil.first_name).all()

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
        join_year_group_choices=JOIN_YEAR_GROUP_CHOICES,
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

    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    tracking_point = get_tracking_point_key(request.values.get('tracking_point'))
    view = (request.values.get('view', 'tracker') or 'tracker').strip().lower()
    if view not in {'tracker', 'overview'}:
        view = 'tracker'
    pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).order_by(Pupil.last_name, Pupil.first_name).all()

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


SUBJECT_SORTABLE_COLUMNS = {'name', 'paper_1_score', 'paper_2_score', 'combined_score', 'combined_percent', 'band_label', 'assessment_year_group', 'progress_delta'}
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

    pupil, error = create_quick_add_pupil(
        school_class=school_class,
        first_name=request.form.get('first_name', ''),
        last_name=request.form.get('last_name', ''),
        gender=request.form.get('gender', ''),
        pupil_premium=request.form.get('pupil_premium') == 'on',
        laps=request.form.get('laps') == 'on',
        service_child=request.form.get('service_child') == 'on',
        send=request.form.get('send') == 'on',
        join_year_group_raw=request.form.get('join_year_group', ''),
        join_date_raw=request.form.get('join_date', ''),
    )
    if error:
        flash(error, 'danger')
        return _quick_add_redirect(redirect_endpoint, context, show_add_pupil='1', **extra_params)
    flash(f'Added {pupil.full_name} to {school_class.name}.', 'success')
    return _quick_add_redirect(redirect_endpoint, context, **extra_params)


def _base_subject_context(subject_key: str) -> dict:
    school_class = get_primary_class_for_user(current_user)
    selected_year = get_selected_academic_year(request.values.get('year'), request.values.get('academic_year'))
    current_year = get_selected_current_academic_year()
    academic_year = selected_year.name
    term = request.values.get('term', get_current_term())
    filters = build_admin_pupil_filter_state(request.values)
    sort_state = build_table_sort_state(
        request.values,
        allowed_columns=WRITING_SORTABLE_COLUMNS if subject_key == 'writing' else SUBJECT_SORTABLE_COLUMNS,
        default_column='name',
    )
    pupils = []
    if school_class:
        pupils = apply_admin_pupil_filters(get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)), filters).all()
    return {
        'subject_key': subject_key,
        'page_title': SUBJECT_META[subject_key]['title'],
        'school_class': school_class,
        'current_year': current_year,
        'academic_year': academic_year,
        'selected_year': selected_year,
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
        assessment_year_group = existing.assessment_year_group if existing and existing.assessment_year_group is not None else pupil.school_class.year_group
        rows.append(
            {
                'pupil': pupil,
                'assessment_year_group': assessment_year_group,
                'paper_1_score': '' if not existing or existing.paper_1_score is None else existing.paper_1_score,
                'paper_2_score': '' if not existing or existing.paper_2_score is None else existing.paper_2_score,
                'combined_score': existing.combined_score if existing else None,
                'combined_percent': existing.combined_percent if existing else None,
                'band_label': existing.band_label if existing else None,
                'notes': existing.notes if existing else '',
                'source': existing.source if existing else None,
                'outcome_theme': get_result_outcome_theme(existing.band_label if existing else None),
                'progress_delta': None,
                'progress_label': '—',
                'progress_theme': None,
                'below_expected_test': False,
            }
        )
    return rows


def _pdf_redirect_url() -> str:
    args = request.args.to_dict(flat=True)
    args.pop('pdf', None)
    if request.endpoint:
        return url_for(request.endpoint, **args)
    return request.referrer or url_for('dashboards.teacher_dashboard')


def export_teacher_subject_pdf(subject_key: str, context: dict, rows: list[dict], anonymise: bool = False):
    current_app.logger.info(
        'PDF export requested subject=%s year=%s row_count=%s anonymise=%s',
        subject_key,
        context['selected_year'].id if context.get('selected_year') else context.get('academic_year'),
        len(rows),
        anonymise,
    )
    try:
        from weasyprint import HTML

        html = render_template(
            'exports/teacher_subject_table_pdf.html',
            subject_key=subject_key,
            subject_label=context['page_title'],
            pupils=context['pupils'],
            rows=rows,
            year=context['selected_year'],
            filters=context['filters'],
            anonymise=anonymise,
            academic_year=context['academic_year'],
            term=context['term'],
            school_class=context['school_class'],
            setting=context.get('setting'),
            generated_at=datetime.now(timezone.utc),
        )
        pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    except Exception:
        current_app.logger.exception(
            'Teacher subject PDF generation failed subject=%s year=%s row_count=%s anonymise=%s',
            subject_key,
            context['selected_year'].id if context.get('selected_year') else context.get('academic_year'),
            len(rows),
            anonymise,
        )
        html = render_template(
            'exports/teacher_subject_table_pdf.html',
            subject_key=subject_key,
            subject_label=context['page_title'],
            pupils=context['pupils'],
            rows=rows,
            year=context['selected_year'],
            filters=context['filters'],
            anonymise=anonymise,
            academic_year=context['academic_year'],
            term=context['term'],
            school_class=context['school_class'],
            setting=context.get('setting'),
            generated_at=datetime.now(timezone.utc),
            pdf_error_message='PDF generation failed. Use browser print/save as PDF.',
        )
        response = make_response(html)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={subject_key}-tracker.pdf'
    return response


def render_subject_page(subject_key: str):
    from app.services.assessment_reliability import apply_result, assessment_health, cohort_year_group, lock_school, school_fingerprint, setting_for_result
    from app.services.assessment_imports import parse_score
    from app.models import AuditLog
    from app.utils import log_audit_event
    from sqlalchemy.exc import SQLAlchemyError
    context = _base_subject_context(subject_key)
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/subject_scores.html', rows=[], setting=None, active_interventions=[], header_state=_table_header_state(context['sort_state'], SUBJECT_SORTABLE_COLUMNS), join_year_group_choices=JOIN_YEAR_GROUP_CHOICES, **context)
    academic_year, term = context['academic_year'], context['term']
    if term not in dict(TERMS):
        from flask import abort
        abort(400)
    all_pupils = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).all()
    pupil_ids = [pupil.id for pupil in all_pupils]
    group = cohort_year_group(all_pupils[0], academic_year) if all_pupils else school_class.year_group
    setting = get_subject_setting(group, subject_key, term, academic_year, school_id=school_class.school_id)
    results = SubjectResult.query.filter(SubjectResult.school_id == school_class.school_id, SubjectResult.pupil_id.in_(pupil_ids), SubjectResult.subject == subject_key, SubjectResult.academic_year == academic_year, SubjectResult.term == term).all()
    existing = {result.pupil_id: result for result in results}
    errors = []
    posted = {}
    if request.method == 'POST':
        form_name = request.form.get('form_name')
        if form_name == 'add_pupil':
            return _handle_quick_add_pupil(school_class, redirect_endpoint=f'teacher.{subject_key}', context=context)
        if form_name != 'results':
            flash('Assessment settings are managed by an admin in Assessment Setup.', 'warning')
            return redirect(url_for('teacher.' + subject_key, academic_year=academic_year, term=term))
        try:
            lock_school(school_class.school_id)
            if request.form.get('baseline') != school_fingerprint(school_class.school_id):
                raise AssessmentValidationError('School data changed while this page was open. Refresh before saving; your submitted scores have been kept below.')
            submitted_ids = {int(key.rsplit('_', 1)[-1]) for key in request.form if key.startswith('paper_1_score_') and key.rsplit('_', 1)[-1].isdigit()}
            if not submitted_ids.issubset(set(pupil_ids)):
                raise AssessmentValidationError('A submitted pupil is outside this class and academic year.')
            saved = created = 0
            for pupil in context['pupils']:
                first_key, second_key = f'paper_1_score_{pupil.id}', f'paper_2_score_{pupil.id}'
                if first_key not in request.form or second_key not in request.form:
                    continue
                raw_first, raw_second = request.form[first_key], request.form[second_key]
                notes = request.form.get(f'notes_{pupil.id}', '').strip()
                posted[pupil.id] = {'paper_1_score': raw_first, 'paper_2_score': raw_second, 'notes': notes, 'assessment_year_group': request.form.get(f'assessment_year_group_{pupil.id}', str(group))}
                try:
                    result = existing.get(pupil.id)
                    row_setting = setting_for_result(result, setting) if result else setting
                    first, second = parse_score(raw_first, row_setting.paper_1_name), parse_score(raw_second, row_setting.paper_2_name)
                    test_group = int(request.form.get(f'assessment_year_group_{pupil.id}', str(group)))
                    if test_group not in range(7):
                        raise AssessmentValidationError('Test level must be between Reception and Year 6.')
                    # Clearing a saved score is deliberate, never inferred from a blank CSV/form.
                    if result and first is None and second is None and request.form.get(f'clear_scores_{pupil.id}') != 'yes':
                        raise AssessmentValidationError('Both scores are blank. Tick “clear scores” to confirm clearing this pupil’s saved scores.')
                    if not result and first is None and second is None and not notes:
                        continue
                    if result is None:
                        created += 1
                        result = SubjectResult(pupil=pupil, pupil_id=pupil.id, school_id=school_class.school_id, academic_year=academic_year, term=term, subject=subject_key)
                    apply_result(result, row_setting, first, second, cohort=cohort_year_group(pupil, academic_year), assessment_year_group=test_group, source='manual')
                    result.notes = notes or None
                    saved += 1
                except (ValueError, AssessmentValidationError) as exc:
                    errors.append(f'{pupil.full_name} — {exc}')
            if errors:
                db.session.rollback()
            else:
                if academic_year == context['current_year']:
                    sync_auto_interventions(school_class, subject_key, term, academic_year, setting.below_are_threshold_percent)
                if created:
                    log_audit_event('assessment_created', 'school_class', school_class.id, school_id=school_class.school_id, details=f'{created} new {subject_key} results; {academic_year} {term}')
                log_audit_event('assessment_bulk_results_changed', 'school_class', school_class.id, school_id=school_class.school_id, details=f'{saved} {subject_key} results saved; {academic_year} {term}')
                db.session.commit()
                flash(f'All changes saved — {saved} {format_subject_name(subject_key)} results. Missing scores are shown in assessment health.', 'success')
                return redirect(url_for('teacher.' + subject_key, academic_year=academic_year, term=term))
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            errors.append(str(exc))
            for pupil in context['pupils']:
                posted[pupil.id] = {key: request.form.get(f'{key}_{pupil.id}', '') for key in ('paper_1_score', 'paper_2_score', 'notes', 'assessment_year_group')}
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Bulk assessment save failed')
            errors.append('No changes were saved because the database could not complete the save. Retry after refreshing.')
            for pupil in context['pupils']:
                posted[pupil.id] = {key: request.form.get(f'{key}_{pupil.id}', '') for key in ('paper_1_score', 'paper_2_score', 'notes', 'assessment_year_group')}
        for error in errors:
            flash(error, 'danger')
    rows = _build_subject_rows(context['pupils'], existing)
    prior = previous_term(term)
    previous = {row.pupil_id: row for row in SubjectResult.query.filter(SubjectResult.pupil_id.in_(pupil_ids), SubjectResult.academic_year == academic_year, SubjectResult.term == prior, SubjectResult.subject == subject_key).all()} if prior else {}
    for row in rows:
        result = existing.get(row['pupil'].id)
        row_setting = setting_for_result(result, setting) if result else setting
        row['paper_1_max'], row['paper_2_max'] = row_setting.paper_1_max, row_setting.paper_2_max
        row['configuration_note'] = f'AT {row_setting.below_are_threshold_percent}% / GDS {row_setting.exceeding_threshold_percent}%; combined maximum {row_setting.combined_max}' if result and result.configuration_snapshot else 'Legacy configuration was not recorded; saved outcome preserved. An explicit edit/recalculation will record the configuration.'
        row['cohort_year_group'] = cohort_year_group(row['pupil'], academic_year)
        row['below_expected_test'] = row['assessment_year_group'] < row['cohort_year_group']
        prev = previous.get(row['pupil'].id)
        delta = row['combined_percent'] - prev.combined_percent if prev and prev.combined_percent is not None and row['combined_percent'] is not None else None
        row.update(progress_delta=delta, progress_label=format_progress_delta(delta), progress_theme=progress_theme(delta))
        row.update(posted.get(row['pupil'].id, {}))
    rows = sort_subject_result_rows(rows, context['sort_state']['column'], context['sort_state']['direction'])
    if request.args.get('pdf') == '1':
        context['setting'] = setting
        return export_teacher_subject_pdf(subject_key, context, rows, anonymise=request.args.get('anonymous') == '1' or request.args.get('anon') == '1')
    active_interventions = Intervention.query.filter_by(school_id=school_class.school_id, subject=subject_key, term=term, academic_year=academic_year, is_active=True).filter(Intervention.pupil_id.in_(pupil_ids)).all()
    return render_template('teacher/subject_scores.html', rows=rows, setting=setting, active_interventions=active_interventions,
        health=assessment_health(all_pupils, existing, setting), baseline=school_fingerprint(school_class.school_id), save_errors=bool(errors),
        header_state=_table_header_state(context['sort_state'], SUBJECT_SORTABLE_COLUMNS), join_year_group_choices=JOIN_YEAR_GROUP_CHOICES, **context)


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

    ghost_by_pupil = {pupil.id: '' for pupil in context['pupils']}
    for pupil in context['pupils']:
        if pupil.id in existing_by_pupil:
            continue
        prior_band = get_latest_previous_assessment(
            pupil_id=pupil.id,
            subject='writing',
            current_term=context['term'],
            academic_year=context['academic_year'],
        )
        if prior_band:
            ghost_by_pupil[pupil.id] = get_writing_band_label(prior_band)

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
                    year=context['selected_year'].id,
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['filters']['search'],
                    gender=context['filters']['gender'],
                    pupil_premium=context['filters']['pupil_premium'],
                    laps=context['filters']['laps'],
                    service_child=context['filters']['service_child'],
                    send=context['filters']['send'],
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
            'ghost_band_label': ghost_by_pupil.get(pupil.id, ''),
            'notes': existing.notes if existing else '',
            'outcome_theme': get_writing_outcome_theme(existing.band if existing else None),
        })
    rows = sort_writing_result_rows(rows, context['sort_state']['column'], context['sort_state']['direction'])
    if request.args.get('pdf') == '1':
        return export_teacher_subject_pdf(
            subject_key='writing',
            context=context,
            rows=rows,
            anonymise=request.args.get('anonymous') == '1' or request.args.get('anon') == '1',
        )
    return render_template(
        'teacher/writing_results.html',
        rows=rows,
        writing_band_choices=WRITING_BAND_CHOICES,
        header_state=_table_header_state(context['sort_state'], WRITING_SORTABLE_COLUMNS),
        join_year_group_choices=JOIN_YEAR_GROUP_CHOICES,
        **context,
    )
