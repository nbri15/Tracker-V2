"""Admin routes for school setup and management."""

from __future__ import annotations

import csv
import io

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import (
    AssessmentSetting,
    GapScore,
    Intervention,
    PhonicsScore,
    Pupil,
    PupilClassHistory,
    SatsColumnResult,
    SatsResult,
    SatsWritingResult,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    User,
    WritingResult,
)
from app.services import (
    BOOLEAN_FILTER_CHOICES,
    CLASS_SORT_OPTIONS,
    CORE_SUBJECTS,
    SATS_COLUMN_SUBJECTS,
    RECEPTION_AREAS,
    RECEPTION_STATUS_CHOICES,
    RECEPTION_TRACKING_POINTS,
    SATS_SCORE_TYPES,
    SATS_TRACKER_MODES,
    SUBGROUP_FILTERS,
    TERMS,
    AssessmentValidationError,
    CsvImportError,
    SatsColumnValidationError,
    apply_admin_pupil_filters,
    build_academic_year_options,
    build_admin_pupil_filter_state,
    build_sort_indicator,
    build_table_sort_state,
    build_class_overview_row,
    build_headline_report,
    build_reception_overview,
    build_reception_summary,
    build_reception_tracker_rows,
    build_phonics_tracker_rows,
    build_times_tables_tracker_rows,
    build_sats_tracker_rows,
    build_subject_overview_cards,
    build_year6_sats_overview,
    build_next_academic_year,
    build_intervention_filters,
    ensure_academic_year,
    ensure_default_logins_and_classes,
    export_class_overview_csv,
    export_history_csv,
    export_interventions_csv,
    export_pupil_overview_csv,
    export_reception_tracker_csv,
    export_sats_results_csv,
    export_sats_tracker_csv,
    export_subject_results_csv,
    export_writing_results_csv,
    format_subject_name,
    generate_csv,
    get_class_detail_context,
    get_current_academic_year,
    get_gender_filter_options,
    get_next_sort_direction,
    get_history_rows,
    get_or_create_assessment_setting,
    get_promotion_mapping_options,
    get_reception_class,
    get_sats_columns,
    get_sats_exam_tabs,
    get_setting_defaults,
    get_tracking_point_key,
    get_tracker_mode,
    get_tracker_mode_label,
    import_combined_results,
    is_ks1_year_group,
    is_times_tables_year_group,
    import_reception_tracker,
    import_sats_tracker_results,
    parse_uploaded_csv,
    promote_pupils_to_next_year,
    recalculate_subject_results_for_scope,
    save_sats_column,
    save_phonics_columns,
    save_phonics_scores,
    sort_phonics_tracker_rows,
    save_times_tables_columns,
    save_times_tables_scores,
    sort_times_tables_tracker_rows,
    save_reception_tracker_entries,
    save_sats_tab,
    set_tracker_mode,
    snapshot_pupil_history,
    sort_class_rows,
    sort_teacher_accounts,
    toggle_sats_column,
    toggle_sats_tab,
    update_assessment_setting,
    ReceptionTrackerValidationError,
    validate_setting_payload,
    add_phonics_column,
    add_times_tables_column,
    ensure_phonics_columns,
    ensure_times_tables_columns,
)
from app.utils import admin_required

from . import admin_bp
from .forms import AssessmentSettingForm


def _active_class_query():
    return SchoolClass.query.filter_by(is_active=True)


def _teacher_options():
    teachers = User.query.filter_by(role='teacher').all()
    return sort_teacher_accounts(teachers)


CLASS_DETAIL_SUBJECT_SORT_COLUMNS = {'name', 'paper_1_score', 'paper_2_score', 'combined_score', 'combined_percent', 'band_label'}
CLASS_DETAIL_WRITING_SORT_COLUMNS = {'name', 'band_label', 'notes'}
PUPIL_STATUS_FILTER_CHOICES = (
    ('active', 'Active pupils only'),
    ('all', 'Include archived pupils'),
    ('archived', 'Archived pupils only'),
)
PUPIL_LINKED_MODELS = (
    ('subject results', SubjectResult),
    ('writing results', WritingResult),
    ('GAP scores', GapScore),
    ('interventions', Intervention),
    ('SATs results', SatsResult),
    ('SATs writing results', SatsWritingResult),
    ('SATs column results', SatsColumnResult),
    ('phonics scores', PhonicsScore),
    ('times tables scores', TimesTableScore),
    ('class history records', PupilClassHistory),
)


def _linked_pupil_record_counts(pupil_id: int) -> dict[str, int]:
    return {
        label: model.query.filter_by(pupil_id=pupil_id).count()
        for label, model in PUPIL_LINKED_MODELS
    }


def _linked_record_summary(linked_counts: dict[str, int]) -> str:
    populated = [f'{label}: {count}' for label, count in linked_counts.items() if count]
    return ', '.join(populated)


def _pupil_action_redirect():
    next_url = request.form.get('next', '').strip()
    return redirect(next_url or url_for('admin.pupils'))


def _table_header_state(sort_state: dict, allowed_columns: set[str]) -> dict:
    return {
        column: {
            'indicator': build_sort_indicator(column, sort_state),
            'next_direction': get_next_sort_direction(column, sort_state),
            'active': sort_state['column'] == column,
        }
        for column in allowed_columns
    }


@admin_bp.route('/classes', methods=['GET', 'POST'])
@login_required
@admin_required
def classes():
    if request.method == 'POST':
        action = request.form.get('action', 'create_class')
        try:
            if action == 'create_class':
                name = request.form.get('name', '').strip()
                year_group = int(request.form.get('year_group', '0'))
                teacher_id_raw = request.form.get('teacher_id', '').strip()
                if not name:
                    raise ValueError('Class name is required.')
                school_class = SchoolClass(name=name, year_group=year_group)
                school_class.teacher_id = int(teacher_id_raw) if teacher_id_raw else None
                school_class.is_active = True
                db.session.add(school_class)
                flash(f'Created class {name}.', 'success')
            elif action == 'update_class':
                school_class = SchoolClass.query.get_or_404(int(request.form.get('class_id', '0')))
                new_name = request.form.get(f'name_{school_class.id}', '').strip()
                new_year_group = int(request.form.get(f'year_group_{school_class.id}', school_class.year_group))
                teacher_id_raw = request.form.get(f'teacher_id_{school_class.id}', '').strip()
                if not new_name:
                    raise ValueError('Class name is required.')
                existing = SchoolClass.query.filter(SchoolClass.name == new_name, SchoolClass.id != school_class.id).first()
                if existing:
                    raise ValueError('A class with that name already exists.')
                school_class.name = new_name
                school_class.year_group = new_year_group
                school_class.teacher_id = int(teacher_id_raw) if teacher_id_raw else None
                school_class.is_active = request.form.get(f'is_active_{school_class.id}') == 'on'
                db.session.add(school_class)
                flash(f'Updated class {school_class.name}.', 'success')
            elif action == 'archive_class':
                school_class = SchoolClass.query.get_or_404(int(request.form.get('class_id', '0')))
                school_class.is_active = False
                db.session.add(school_class)
                flash(f'Archived class {school_class.name}.', 'success')
            db.session.commit()
            return redirect(url_for('admin.classes'))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Class changes could not be saved: {exc}', 'danger')

    academic_year = request.args.get('academic_year', get_current_academic_year())
    filter_year_group = request.args.get('year_group', '').strip()
    filter_teacher = request.args.get('teacher_id', '').strip()
    filter_class = request.args.get('class_id', '').strip()
    subgroup = request.args.get('subgroup', 'all').strip() or 'all'
    sort = request.args.get('sort', 'year_group')

    query = SchoolClass.query
    if filter_year_group:
        query = query.filter(SchoolClass.year_group == int(filter_year_group))
    if filter_teacher:
        query = query.filter(SchoolClass.teacher_id == int(filter_teacher))
    if filter_class:
        query = query.filter(SchoolClass.id == int(filter_class))

    classes = query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    rows = [build_class_overview_row(school_class, academic_year, subgroup) for school_class in classes]
    rows = sort_class_rows(rows, sort)
    return render_template(
        'admin/classes.html',
        classes=rows,
        academic_year=academic_year,
        filter_year_group=filter_year_group,
        filter_teacher=filter_teacher,
        filter_class=filter_class,
        sort=sort,
        subgroup=subgroup,
        subgroup_filters=SUBGROUP_FILTERS,
        sort_options=CLASS_SORT_OPTIONS,
        teacher_options=_teacher_options(),
        class_options=SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all(),
    )


@admin_bp.route('/classes/<int:class_id>')
@login_required
@admin_required
def class_detail(class_id: int):
    academic_year = request.args.get('academic_year', get_current_academic_year())
    school_class = SchoolClass.query.get_or_404(class_id)
    pupil_filters = build_admin_pupil_filter_state(request.args)
    selected_subject = request.args.get('subject', 'maths').strip() or 'maths'
    selected_term = request.args.get('term', '').strip() or None
    allowed_columns = CLASS_DETAIL_WRITING_SORT_COLUMNS if selected_subject == 'writing' else CLASS_DETAIL_SUBJECT_SORT_COLUMNS
    sort_state = build_table_sort_state(request.args, allowed_columns=allowed_columns, default_column='name')
    context = get_class_detail_context(
        school_class,
        academic_year,
        subject=selected_subject,
        term=selected_term,
        filters=pupil_filters,
        sort_column=sort_state['column'],
        sort_direction=sort_state['direction'],
    )
    if context['selected_subject'] == 'writing':
        header_state = _table_header_state(sort_state, CLASS_DETAIL_WRITING_SORT_COLUMNS)
    elif context['selected_subject'] in {'maths', 'reading', 'spag'}:
        header_state = _table_header_state(sort_state, CLASS_DETAIL_SUBJECT_SORT_COLUMNS)
    else:
        header_state = {}
    return render_template(
        'admin/class_detail.html',
        academic_year=academic_year,
        boolean_filter_choices=BOOLEAN_FILTER_CHOICES,
        gender_options=get_gender_filter_options(
            class_id=school_class.id,
            include_inactive=pupil_filters.get('pupil_status') != 'active',
        ),
        pupil_status_filter_choices=PUPIL_STATUS_FILTER_CHOICES,
        sort_state=sort_state,
        header_state=header_state,
        **context,
    )


@admin_bp.route('/classes/<int:class_id>/sats')
@login_required
@admin_required
def class_sats(class_id: int):
    school_class = SchoolClass.query.get_or_404(class_id)
    academic_year = request.args.get('academic_year', get_current_academic_year())
    selected_tab_id_raw = request.args.get('exam_tab_id', '').strip()
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    columns, rows, overview = build_sats_tracker_rows(pupils, academic_year, 6, exam_tab_id=int(selected_tab_id_raw) if selected_tab_id_raw else None, active_only=True)
    selected_tab = overview.pop('_selected_tab', None)
    tabs = overview.pop('_tabs', get_sats_exam_tabs(6, include_inactive=True))
    return render_template(
        'admin/sats.html',
        academic_year=academic_year,
        tracker_mode=get_tracker_mode(6),
        tracker_mode_label=get_tracker_mode_label(6),
        tracker_mode_options=SATS_TRACKER_MODES,
        class_options=SchoolClass.query.filter_by(year_group=6).order_by(SchoolClass.name).all(),
        selected_class_id=school_class.id,
        columns=columns,
        all_columns=get_sats_columns(6, exam_tab_id=selected_tab.id if selected_tab else None, active_only=False),
        tabs=tabs,
        selected_tab=selected_tab,
        rows=rows,
        overview=overview,
        class_summaries=[{'class': school_class, 'rows': rows, 'subject_totals': overview}],
        sats_subject_choices=SATS_COLUMN_SUBJECTS,
        sats_score_type_choices=SATS_SCORE_TYPES,
    )


@admin_bp.route('/classes/<int:class_id>/phonics', methods=['GET', 'POST'])
@login_required
@admin_required
def class_phonics(class_id: int):
    school_class = SchoolClass.query.get_or_404(class_id)
    academic_year = request.values.get('academic_year', get_current_academic_year())
    filters = build_admin_pupil_filter_state(request.values)

    if not is_ks1_year_group(school_class.year_group):
        flash('The phonics tracker is only available for Year 1 and Year 2 classes.', 'warning')
        return redirect(url_for('admin.class_detail', class_id=class_id, academic_year=academic_year))

    pupils = apply_admin_pupil_filters(school_class.pupils.filter_by(is_active=True), filters).order_by(Pupil.last_name, Pupil.first_name).all()
    columns = ensure_phonics_columns(school_class.year_group)
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
                columns = save_phonics_columns(school_class.year_group, request.form)
                flash('Phonics test columns updated.', 'success')
            elif action == 'add_column':
                column = add_phonics_column(school_class.year_group, request.form)
                flash(f'Added phonics column {column.name}.', 'success')
            else:
                save_phonics_scores(pupils, columns, academic_year, request.form)
                flash('Phonics scores saved.', 'success')
            db.session.commit()
            return redirect(url_for('admin.class_phonics', class_id=class_id, academic_year=academic_year, pupil_status=filters['pupil_status'], gender=filters['gender'], pupil_premium=filters['pupil_premium'], laps=filters['laps'], service_child=filters['service_child'], search=filters['search'], sort=sort_state['column'], direction=sort_state['direction']))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Phonics changes could not be saved: {exc}', 'danger')
            columns = ensure_phonics_columns(school_class.year_group)

    rows = build_phonics_tracker_rows(pupils, columns, academic_year)
    rows = sort_phonics_tracker_rows(rows, sort_state['column'], sort_state['direction'])
    return render_template(
        'admin/class_phonics.html',
        school_class=school_class,
        columns=columns,
        rows=rows,
        pupils=pupils,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        boolean_filter_choices=BOOLEAN_FILTER_CHOICES,
        gender_options=get_gender_filter_options(
            class_id=school_class.id,
            include_inactive=filters.get('pupil_status') != 'active',
        ),
        pupil_status_filter_choices=PUPIL_STATUS_FILTER_CHOICES,
        sort_state=sort_state,
        header_state=header_state,
    )


@admin_bp.route('/classes/<int:class_id>/times_tables', methods=['GET', 'POST'])
@login_required
@admin_required
def class_times_tables(class_id: int):
    school_class = SchoolClass.query.get_or_404(class_id)
    academic_year = request.values.get('academic_year', get_current_academic_year())
    filters = build_admin_pupil_filter_state(request.values)

    if not is_times_tables_year_group(school_class.year_group):
        flash('The times tables tracker is only available for Year 4 classes.', 'warning')
        return redirect(url_for('admin.class_detail', class_id=class_id, academic_year=academic_year))

    pupils = apply_admin_pupil_filters(school_class.pupils.filter_by(is_active=True), filters).order_by(Pupil.last_name, Pupil.first_name).all()
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
            return redirect(url_for('admin.class_times_tables', class_id=class_id, academic_year=academic_year, pupil_status=filters['pupil_status'], gender=filters['gender'], pupil_premium=filters['pupil_premium'], laps=filters['laps'], service_child=filters['service_child'], search=filters['search'], sort=sort_state['column'], direction=sort_state['direction']))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Times tables changes could not be saved: {exc}', 'danger')
            columns = ensure_times_tables_columns(school_class.year_group)

    rows = build_times_tables_tracker_rows(pupils, columns, academic_year)
    rows = sort_times_tables_tracker_rows(rows, sort_state['column'], sort_state['direction'])
    return render_template(
        'admin/class_times_tables.html',
        school_class=school_class,
        columns=columns,
        rows=rows,
        pupils=pupils,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        boolean_filter_choices=BOOLEAN_FILTER_CHOICES,
        gender_options=get_gender_filter_options(
            class_id=school_class.id,
            include_inactive=filters.get('pupil_status') != 'active',
        ),
        pupil_status_filter_choices=PUPIL_STATUS_FILTER_CHOICES,
        sort_state=sort_state,
        header_state=header_state,
    )


@admin_bp.route('/reception', methods=['GET', 'POST'])
@login_required
@admin_required
def reception_tracker():
    school_class = get_reception_class()
    if not school_class:
        flash('Reception class has not been created yet. Open Users and run Sync defaults or create Reception class.', 'warning')
        return redirect(url_for('admin.classes'))

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
            return redirect(url_for('admin.reception_tracker', academic_year=academic_year, tracking_point=tracking_point, view=view))
        except ReceptionTrackerValidationError as exc:
            db.session.rollback()
            flash(f'Reception tracker could not be saved: {exc}', 'danger')

    rows = build_reception_tracker_rows(pupils, academic_year, tracking_point)
    summary = build_reception_summary(rows)
    overview = build_reception_overview(rows)
    return render_template(
        'admin/reception_tracker.html',
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


@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    if request.method == 'POST':
        action = request.form.get('action', 'create')
        try:
            if action == 'create':
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '').strip()
                class_id_raw = request.form.get('class_id', '').strip()
                if not username or not password:
                    raise ValueError('Username and password are required.')
                if User.query.filter_by(username=username).first():
                    raise ValueError('That username already exists.')
                user = User(username=username, role='teacher', is_active=True)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
                if class_id_raw:
                    school_class = SchoolClass.query.get_or_404(int(class_id_raw))
                    school_class.teacher_id = user.id
                    db.session.add(school_class)
                flash(f'Created teacher user {username}.', 'success')
            elif action == 'update':
                user = User.query.get_or_404(int(request.form.get('user_id', '0')))
                username = request.form.get(f'username_{user.id}', '').strip()
                password = request.form.get(f'password_{user.id}', '').strip()
                class_id_raw = request.form.get(f'class_id_{user.id}', '').strip()
                if username and username != user.username:
                    if User.query.filter(User.username == username, User.id != user.id).first():
                        raise ValueError('That username is already in use.')
                    user.username = username
                user.is_active = request.form.get(f'is_active_{user.id}') == 'on'
                if password:
                    user.set_password(password)
                for school_class in user.classes.all():
                    if not class_id_raw or school_class.id != int(class_id_raw):
                        school_class.teacher_id = None
                        db.session.add(school_class)
                if class_id_raw:
                    school_class = SchoolClass.query.get_or_404(int(class_id_raw))
                    school_class.teacher_id = user.id
                    db.session.add(school_class)
                db.session.add(user)
                flash(f'Updated {user.username}.', 'success')
            elif action == 'sync_defaults':
                ensure_default_logins_and_classes()
                flash('Default admin, teacher logins, and Year 1–6 classes were refreshed.', 'success')
            db.session.commit()
            return redirect(url_for('admin.users'))
        except ValueError as exc:
            db.session.rollback()
            flash(f'User changes could not be saved: {exc}', 'danger')

    teachers = sort_teacher_accounts(User.query.order_by(User.role.desc(), User.username).all())
    classes = SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    return render_template('admin/users.html', teachers=teachers, classes=classes)


@admin_bp.route('/pupils')
@login_required
@admin_required
def pupils():
    pupil_filters = build_admin_pupil_filter_state(request.args)
    class_id_raw = request.args.get('class_id', '').strip()

    query = apply_admin_pupil_filters(Pupil.query, pupil_filters)
    if class_id_raw:
        query = query.filter(Pupil.class_id == int(class_id_raw))
    pupils = query.order_by(Pupil.last_name, Pupil.first_name).all()
    return render_template(
        'admin/pupils.html',
        pupils=pupils,
        pupil_filters=pupil_filters,
        pupil_status_filter_choices=PUPIL_STATUS_FILTER_CHOICES,
        class_id_filter=class_id_raw,
        class_options=SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all(),
    )


@admin_bp.route('/pupils/manage', methods=['POST'])
@login_required
@admin_required
def manage_pupil():
    pupil = Pupil.query.get_or_404(int(request.form.get('pupil_id', '0')))
    action = request.form.get('action', '').strip()
    linked_counts = _linked_pupil_record_counts(pupil.id)
    has_linked_data = any(linked_counts.values())

    try:
        if action == 'archive':
            pupil.is_active = False
            db.session.add(pupil)
            db.session.commit()
            flash(f'Archived {pupil.full_name}. They are now hidden from active lists.', 'success')
        elif action == 'restore':
            pupil.is_active = True
            db.session.add(pupil)
            db.session.commit()
            flash(f'Restored {pupil.full_name}. They are active again.', 'success')
        elif action == 'delete':
            if has_linked_data:
                summary = _linked_record_summary(linked_counts)
                flash(
                    f'Permanent delete blocked for {pupil.full_name}. Linked data exists ({summary}). Archive this pupil instead.',
                    'danger',
                )
                return _pupil_action_redirect()
            db.session.delete(pupil)
            db.session.commit()
            flash(f'Permanently deleted {pupil.full_name}.', 'success')
        else:
            flash('Unknown pupil action.', 'warning')
    except ValueError as exc:
        db.session.rollback()
        flash(f'Pupil action failed: {exc}', 'danger')
    return _pupil_action_redirect()


def _parse_setting_form(prefix: str = '') -> dict:
    suffix = f'_{prefix}' if prefix else ''
    below_threshold = float(request.form.get(f'below_are_threshold_percent{suffix}', '0') or 0)
    return {
        'year_group': int(request.form.get(f'year_group{suffix}', '0')),
        'subject': request.form.get(f'subject{suffix}', '').strip(),
        'term': request.form.get(f'term{suffix}', '').strip(),
        'paper_1_name': request.form.get(f'paper_1_name{suffix}', '').strip(),
        'paper_1_max': int(request.form.get(f'paper_1_max{suffix}', '0')),
        'paper_2_name': request.form.get(f'paper_2_name{suffix}', '').strip(),
        'paper_2_max': int(request.form.get(f'paper_2_max{suffix}', '0')),
        'combined_max': int(request.form.get(f'combined_max{suffix}', '0') or 0),
        'below_are_threshold_percent': below_threshold,
        'on_track_threshold_percent': below_threshold,
        'exceeding_threshold_percent': float(request.form.get(f'exceeding_threshold_percent{suffix}', '0') or 0),
    }


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    form = AssessmentSettingForm()
    filter_year_group = request.args.get('year_group', '').strip()
    filter_subject = request.args.get('subject', '').strip()
    filter_term = request.args.get('term', '').strip()

    if request.method == 'POST':
        action = request.form.get('action', 'create')
        try:
            if action == 'create':
                payload = validate_setting_payload(_parse_setting_form())
                setting = get_or_create_assessment_setting(payload['year_group'], payload['subject'], payload['term'])
                update_assessment_setting(setting, payload)
                recalculate_subject_results_for_scope(setting.year_group, setting.subject, setting.term)
                db.session.commit()
                flash(f"Saved {format_subject_name(setting.subject)} {setting.term.title()} settings for Year {setting.year_group}.", 'success')
            else:
                setting_id = int(request.form.get('setting_id', '0'))
                setting = AssessmentSetting.query.get_or_404(setting_id)
                payload = validate_setting_payload(_parse_setting_form(prefix=str(setting.id)))
                existing = AssessmentSetting.query.filter_by(year_group=payload['year_group'], subject=payload['subject'], term=payload['term']).first()
                if existing and existing.id != setting.id:
                    raise AssessmentValidationError('A setting already exists for that year group, subject, and term.')
                update_assessment_setting(setting, payload)
                recalculate_subject_results_for_scope(setting.year_group, setting.subject, setting.term)
                db.session.commit()
                flash(f"Updated {format_subject_name(setting.subject)} {setting.term.title()} settings for Year {setting.year_group}.", 'success')
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'Settings could not be saved: {exc}', 'danger')

    settings_query = AssessmentSetting.query
    if filter_year_group:
        settings_query = settings_query.filter(AssessmentSetting.year_group == int(filter_year_group))
    if filter_subject:
        settings_query = settings_query.filter(AssessmentSetting.subject == filter_subject)
    if filter_term:
        settings_query = settings_query.filter(AssessmentSetting.term == filter_term)

    settings = settings_query.order_by(AssessmentSetting.year_group, AssessmentSetting.subject, AssessmentSetting.term).all()

    if request.method == 'GET' and filter_year_group and filter_subject and filter_term:
        form.year_group.data = int(filter_year_group)
        form.subject.data = filter_subject
        form.term.data = filter_term
        setting = AssessmentSetting.query.filter_by(year_group=int(filter_year_group), subject=filter_subject, term=filter_term).first()
        if setting:
            form.paper_1_name.data = setting.paper_1_name
            form.paper_1_max.data = setting.paper_1_max
            form.paper_2_name.data = setting.paper_2_name
            form.paper_2_max.data = setting.paper_2_max
            form.combined_max.data = setting.combined_max
            form.below_are_threshold_percent.data = setting.below_are_threshold_percent
            form.on_track_threshold_percent.data = setting.on_track_threshold_percent
            form.exceeding_threshold_percent.data = setting.exceeding_threshold_percent
        elif filter_subject in CORE_SUBJECTS:
            defaults = get_setting_defaults(filter_subject)
            form.paper_1_name.data = defaults['paper_1_name']
            form.paper_1_max.data = defaults['paper_1_max']
            form.paper_2_name.data = defaults['paper_2_name']
            form.paper_2_max.data = defaults['paper_2_max']
            form.combined_max.data = defaults['combined_max']
            form.below_are_threshold_percent.data = defaults['below_are_threshold_percent']
            form.on_track_threshold_percent.data = defaults['on_track_threshold_percent']
            form.exceeding_threshold_percent.data = defaults['exceeding_threshold_percent']

    return render_template(
        'admin/settings.html',
        settings=settings,
        filter_year_group=filter_year_group,
        filter_subject=filter_subject,
        filter_term=filter_term,
        filter_subject_choices=[('', 'All subjects')] + [(subject, format_subject_name(subject)) for subject in CORE_SUBJECTS],
        filter_term_choices=[('', 'All terms')] + TERMS,
        form=form,
        terms=TERMS,
    )


@admin_bp.route('/interventions')
@login_required
@admin_required
def interventions():
    from app.models import Intervention

    academic_year = request.args.get('academic_year', get_current_academic_year())
    year_group = request.args.get('year_group', '').strip()
    class_id = request.args.get('class_id', '').strip()
    subject = request.args.get('subject', '').strip()
    status = request.args.get('status', 'active').strip() or 'active'

    query = Intervention.query.join(Intervention.pupil)
    query = query.filter(Intervention.academic_year == academic_year)
    query = build_intervention_filters(query, year_group=year_group, class_id=class_id, subject=subject, status=status)
    rows = query.order_by(Intervention.is_active.desc(), Pupil.last_name, Pupil.first_name).all()

    return render_template(
        'admin/interventions.html',
        interventions=rows,
        academic_year=academic_year,
        year_group=year_group,
        class_id=class_id,
        subject=subject,
        status=status,
        class_options=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all(),
        subjects=CORE_SUBJECTS,
    )


@admin_bp.route('/sats', methods=['GET', 'POST'])
@login_required
@admin_required
def sats():
    academic_year = request.values.get('academic_year', get_current_academic_year())
    selected_class_id = request.values.get('class_id', '').strip()
    selected_tab_id_raw = request.values.get('exam_tab_id', '').strip()

    if request.method == 'POST':
        action = request.form.get('action', 'update_mode')
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
                flash(f"{column.name} is now {'shown' if column.is_active else 'hidden'}.", 'success')
            db.session.commit()
            return redirect(url_for('admin.sats', academic_year=academic_year, class_id=selected_class_id or None, exam_tab_id=selected_tab_id_raw or None))
        except (ValueError, SatsColumnValidationError) as exc:
            db.session.rollback()
            flash(f'SATs changes could not be saved: {exc}', 'danger')

    overview = build_year6_sats_overview(
        academic_year,
        class_id=int(selected_class_id) if selected_class_id else None,
        exam_tab_id=int(selected_tab_id_raw) if selected_tab_id_raw else None,
    )
    return render_template(
        'admin/sats.html',
        academic_year=academic_year,
        tracker_mode=get_tracker_mode(6),
        tracker_mode_label=get_tracker_mode_label(6),
        tracker_mode_options=SATS_TRACKER_MODES,
        class_options=SchoolClass.query.filter_by(year_group=6).order_by(SchoolClass.name).all(),
        selected_class_id=int(selected_class_id) if selected_class_id else None,
        columns=overview['columns'],
        all_columns=get_sats_columns(6, exam_tab_id=overview['selected_tab'].id if overview.get('selected_tab') else None, active_only=False),
        tabs=overview['tabs'],
        selected_tab=overview['selected_tab'],
        rows=overview['rows'],
        overview=overview['class_summaries'][0]['subject_totals'] if len(overview['class_summaries']) == 1 else {},
        class_summaries=overview['class_summaries'],
        sats_subject_choices=SATS_COLUMN_SUBJECTS,
        sats_score_type_choices=SATS_SCORE_TYPES,
    )


@admin_bp.route('/promotion', methods=['GET', 'POST'])
@login_required
@admin_required
def promotion():
    academic_year = request.values.get('academic_year', get_current_academic_year())
    next_year = build_next_academic_year(academic_year)
    mapping_rows = get_promotion_mapping_options()
    if request.method == 'POST':
        action = request.form.get('action', 'snapshot')
        try:
            if action == 'snapshot':
                count = snapshot_pupil_history(academic_year)
                ensure_academic_year(academic_year, mark_current=True)
                db.session.commit()
                flash(f'Archived {count} pupil class history record(s) for {academic_year}.', 'success')
            elif action == 'promote':
                class_mapping: dict[int, int | None] = {}
                for row in mapping_rows:
                    source_class = row['source_class']
                    destination_choices = row['destination_classes']
                    selected_value = (request.form.get(f'destination_{source_class.id}') or '').strip()
                    if destination_choices:
                        if not selected_value:
                            raise ValueError(f'Please choose a destination class for {source_class.name}.')
                        if not selected_value.isdigit():
                            raise ValueError(f'Invalid destination class selected for {source_class.name}.')
                        selected_id = int(selected_value)
                        valid_ids = {item.id for item in destination_choices}
                        if selected_id not in valid_ids:
                            raise ValueError(f'Invalid destination class selected for {source_class.name}.')
                        class_mapping[source_class.id] = selected_id
                    else:
                        class_mapping[source_class.id] = None
                outcome = promote_pupils_to_next_year(academic_year, class_mapping=class_mapping)
                db.session.commit()
                flash(f"Promotion complete. Moved {outcome['moved']} pupil(s), marked {outcome['leavers']} Year 6 leavers, and set {outcome['target_year']} as current.", 'success')
            return redirect(url_for('admin.promotion', academic_year=academic_year))
        except ValueError as exc:
            db.session.rollback()
            flash(f'Promotion changes could not be saved: {exc}', 'danger')

    history_rows = get_history_rows(academic_year)
    return render_template(
        'admin/promotion.html',
        academic_year=academic_year,
        next_year=next_year,
        history_rows=history_rows,
        mapping_rows=mapping_rows,
    )


@admin_bp.route('/imports', methods=['GET', 'POST'])
@login_required
@admin_required
def imports():
    summary = None
    selected_import_type = 'combined'
    if request.method == 'POST':
        selected_import_type = request.form.get('import_type', 'combined')
        try:
            rows = parse_uploaded_csv(request.files.get('csv_file'))
            if selected_import_type == 'combined':
                summary = import_combined_results(rows)
            elif selected_import_type == 'reception':
                summary = import_reception_tracker(rows)
            elif selected_import_type == 'sats_tracker':
                summary = import_sats_tracker_results(rows)
            else:
                raise CsvImportError('Unknown import type.')
            db.session.commit()
            if summary.errors:
                for error in summary.errors[:20]:
                    flash(error, 'warning')
            flash(
                f'Import finished: rows processed {summary.rows_processed}, pupils matched {summary.pupils_matched}, '
                f'rows skipped {summary.rows_skipped}, tracker entries created {summary.tracker_entries_created}, '
                f'tracker entries updated {summary.tracker_entries_updated}, created {summary.created}, updated {summary.updated}, '
                f'manual/protected results skipped {summary.manual_results_skipped}, validation errors {summary.validation_errors}.',
                'success',
            )
        except CsvImportError as exc:
            db.session.rollback()
            flash(f'Import failed: {exc}', 'danger')

    overview = {'teachers': User.query.filter_by(role='teacher').count(), 'classes': SchoolClass.query.count(), 'pupils': Pupil.query.count()}
    return render_template(
        'admin/imports.html',
        overview=overview,
        class_options=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all(),
        current_year=get_current_academic_year(),
        reception_tracking_points=RECEPTION_TRACKING_POINTS,
        sats_tabs=get_sats_exam_tabs(6, include_inactive=False),
        summary=summary,
        selected_import_type=selected_import_type,
    )


@admin_bp.route('/imports/template/<template_type>')
@login_required
@admin_required
def download_import_template(template_type: str):
    template_map = {'combined', 'reception', 'sats_tracker'}
    if template_type not in template_map:
        flash('Unknown template type.', 'warning')
        return redirect(url_for('admin.imports'))
    csv_text = generate_csv(template_type)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={template_type}_template.csv'})


@admin_bp.route('/reports/headline')
@login_required
@admin_required
def headline_report():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    subject = (request.args.get('subject', 'maths') or 'maths').strip().lower()
    tracker_key = (request.args.get('tracker_key', '') or '').strip()
    year_group_raw = request.args.get('year_group', '').strip()
    year_group = int(year_group_raw) if year_group_raw.isdigit() else None
    if subject == 'eyfs' and year_group is None:
        year_group_raw = '0'
        year_group = 0
    if subject == 'times_tables' and year_group is None:
        year_group_raw = '4'
        year_group = 4
    if subject == 'sats' and year_group is None:
        year_group_raw = '6'
        year_group = 6
    subgroup = (request.args.get('subgroup', 'all') or 'all').strip() or 'all'
    pupil_filters = build_admin_pupil_filter_state(request.args)
    report = build_headline_report(
        subject=subject,
        academic_year=academic_year,
        year_group=year_group,
        subgroup=subgroup,
        filters=pupil_filters,
        tracker_key=tracker_key or None,
    )
    tracker_options = []
    if subject == 'eyfs':
        tracker_options = [{'value': '', 'label': 'All tracking points'}] + [
            {'value': key, 'label': label} for key, label in RECEPTION_TRACKING_POINTS
        ]
    elif subject == 'phonics':
        phonics_years = [year_group] if year_group in {1, 2} else [1, 2]
        for year in phonics_years:
            for column in ensure_phonics_columns(year):
                tracker_options.append({'value': str(column.id), 'label': f'Year {year} · {column.name}'})
    elif subject == 'times_tables':
        for column in ensure_times_tables_columns(4):
            tracker_options.append({'value': str(column.id), 'label': column.name})
    elif subject == 'sats':
        tracker_options = [{'value': '', 'label': 'Latest active exam tab'}] + [
            {'value': str(tab.id), 'label': tab.name} for tab in get_sats_exam_tabs(6, include_inactive=False)
        ]
    return render_template(
        'admin/headline_report.html',
        report=report,
        subject=subject,
        tracker_key=tracker_key,
        tracker_options=tracker_options,
        academic_year=academic_year,
        year_group=year_group_raw,
        subgroup=subgroup,
        pupil_filters=pupil_filters,
        subjects=['writing', 'reading', 'maths', 'spag', 'eyfs', 'phonics', 'times_tables', 'sats'],
        subgroup_filters=SUBGROUP_FILTERS,
        boolean_filter_choices=BOOLEAN_FILTER_CHOICES,
    )


@admin_bp.route('/reports/headline/export')
@login_required
@admin_required
def export_headline_report():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    subject = (request.args.get('subject', 'maths') or 'maths').strip().lower()
    tracker_key = (request.args.get('tracker_key', '') or '').strip()
    year_group_raw = request.args.get('year_group', '').strip()
    year_group = int(year_group_raw) if year_group_raw.isdigit() else None
    if subject == 'eyfs' and year_group is None:
        year_group = 0
    if subject == 'times_tables' and year_group is None:
        year_group = 4
    if subject == 'sats' and year_group is None:
        year_group = 6
    subgroup = (request.args.get('subgroup', 'all') or 'all').strip() or 'all'
    pupil_filters = build_admin_pupil_filter_state(request.args)
    report = build_headline_report(
        subject=subject,
        academic_year=academic_year,
        year_group=year_group,
        subgroup=subgroup,
        filters=pupil_filters,
        tracker_key=tracker_key or None,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Headline report'])
    writer.writerow(['Subject', report['subject_label']])
    writer.writerow(['Academic year', academic_year])
    writer.writerow(['Year group', f"Year {year_group}" if year_group else 'Whole school'])
    writer.writerow(['Subgroup', SUBGROUP_FILTERS.get(subgroup, subgroup.title())])
    writer.writerow([])
    header = [report.get('row_header_label', 'Year group')]
    for term in report['buckets']:
        term_label = report['bucket_labels'][term]
        for measure_key in report['measure_keys']:
            header.append(f"{term_label} {report['measure_labels'][measure_key]}")
    writer.writerow(header)
    for row in report['rows']:
        row_data = [row.get('label') or f"Year {row.get('year_group', '')}".strip()]
        for term in report['buckets']:
            for measure_key in report['measure_keys']:
                row_data.append(row['cells'][term][measure_key]['display'])
        writer.writerow(row_data)
    total_row = ['Whole school']
    for term in report['buckets']:
        for measure_key in report['measure_keys']:
            total_row.append(report['totals'][term][measure_key]['display'])
    writer.writerow(total_row)
    csv_text = output.getvalue()
    filename_subject = subject if subject in {'maths', 'reading', 'spag', 'writing', 'eyfs', 'phonics', 'times_tables', 'sats'} else 'headline'
    return Response(
        csv_text,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=headline_{filename_subject}_{academic_year.replace("/", "-")}.csv'},
    )


@admin_bp.route('/exports/subject-results')
@login_required
@admin_required
def export_subject_results():
    csv_text = export_subject_results_csv(
        class_id=int(request.args['class_id']) if request.args.get('class_id') else None,
        subject=request.args.get('subject') or None,
        academic_year=request.args.get('academic_year') or None,
        term=request.args.get('term') or None,
    )
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=subject_results_export.csv'})


@admin_bp.route('/exports/writing-results')
@login_required
@admin_required
def export_writing_results():
    csv_text = export_writing_results_csv(
        class_id=int(request.args['class_id']) if request.args.get('class_id') else None,
        academic_year=request.args.get('academic_year') or None,
        term=request.args.get('term') or None,
    )
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=writing_results_export.csv'})


@admin_bp.route('/exports/class-overview')
@login_required
@admin_required
def export_class_overview():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    csv_text = export_class_overview_csv(academic_year, class_id=int(request.args['class_id']) if request.args.get('class_id') else None)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=class_overview_export.csv'})


@admin_bp.route('/exports/pupil-overview')
@login_required
@admin_required
def export_pupil_overview():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    csv_text = export_pupil_overview_csv(academic_year, class_id=int(request.args['class_id']) if request.args.get('class_id') else None)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=pupil_overview_export.csv'})


@admin_bp.route('/exports/sats')
@login_required
@admin_required
def export_sats():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    csv_text = export_sats_results_csv(
        academic_year,
        class_id=int(request.args['class_id']) if request.args.get('class_id') else None,
        exam_tab_id=int(request.args['exam_tab_id']) if request.args.get('exam_tab_id') else None,
    )
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=sats_export.csv'})


@admin_bp.route('/exports/reception-tracker')
@login_required
@admin_required
def export_reception_tracker():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    tracking_point = request.args.get('tracking_point', RECEPTION_TRACKING_POINTS[0][0]).strip().lower()
    csv_text = export_reception_tracker_csv(academic_year, tracking_point)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=reception_tracker_export.csv'})


@admin_bp.route('/exports/sats-tracker')
@login_required
@admin_required
def export_sats_tracker():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    exam_tab = request.args.get('exam_tab', '').strip()
    if not exam_tab:
        flash('Choose an exam tab for the SATs tracker export.', 'warning')
        return redirect(url_for('admin.imports'))
    try:
        csv_text = export_sats_tracker_csv(academic_year, exam_tab)
    except CsvImportError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('admin.imports'))
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=year6_sats_tracker_export.csv'})


@admin_bp.route('/exports/interventions')
@login_required
@admin_required
def export_interventions():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    csv_text = export_interventions_csv(academic_year, class_id=int(request.args['class_id']) if request.args.get('class_id') else None)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=interventions_export.csv'})


@admin_bp.route('/exports/history')
@login_required
@admin_required
def export_history():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    csv_text = export_history_csv(academic_year)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=promotion_history_export.csv'})
