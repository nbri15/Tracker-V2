"""Admin routes for school setup and management."""

from __future__ import annotations

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import AssessmentSetting, Intervention, Pupil, SatsResult, SatsWritingResult, SchoolClass, SubjectResult, User
from app.services import (
    CLASS_SORT_OPTIONS,
    CORE_SUBJECTS,
    SATS_ASSESSMENT_POINTS,
    SATS_SUBJECTS,
    SUBGROUP_FILTERS,
    TERMS,
    AssessmentValidationError,
    CsvImportError,
    build_class_overview_row,
    build_intervention_filters,
    build_year6_sats_summary,
    export_subject_results_csv,
    export_writing_results_csv,
    format_subject_name,
    generate_csv,
    get_class_detail_context,
    get_current_academic_year,
    get_or_create_assessment_setting,
    get_setting_defaults,
    get_sats_subject_summary,
    get_sats_writing_summary,
    import_pupils,
    import_subject_results,
    import_writing_results,
    parse_uploaded_csv,
    sort_class_rows,
    update_assessment_setting,
    validate_setting_payload,
)
from app.utils import admin_required

from . import admin_bp
from .forms import AssessmentSettingForm


@admin_bp.route('/classes', methods=['GET', 'POST'])
@login_required
@admin_required
def classes():
    """List available classes and handle teacher assignment updates."""

    if request.method == 'POST':
        action = request.form.get('action', 'assign_teacher')
        try:
            if action == 'assign_teacher':
                school_class = SchoolClass.query.get_or_404(int(request.form.get('class_id', '0')))
                teacher_id_raw = request.form.get('teacher_id', '').strip()
                school_class.teacher_id = int(teacher_id_raw) if teacher_id_raw else None
                db.session.add(school_class)
                flash(f'Teacher assignment updated for {school_class.name}.', 'success')
            elif action == 'create_class':
                name = request.form.get('name', '').strip()
                year_group = int(request.form.get('year_group', '0'))
                teacher_id_raw = request.form.get('teacher_id', '').strip()
                if not name:
                    raise ValueError('Class name is required.')
                existing = SchoolClass.query.filter_by(name=name).first()
                if existing:
                    raise ValueError('A class with that name already exists.')
                school_class = SchoolClass(name=name, year_group=year_group, teacher_id=int(teacher_id_raw) if teacher_id_raw else None)
                db.session.add(school_class)
                flash(f'Created class {name}.', 'success')
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

    query = SchoolClass.query.filter_by(is_active=True)
    if filter_year_group:
        query = query.filter(SchoolClass.year_group == int(filter_year_group))
    if filter_teacher:
        query = query.filter(SchoolClass.teacher_id == int(filter_teacher))
    if filter_class:
        query = query.filter(SchoolClass.id == int(filter_class))

    classes = query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    rows = [build_class_overview_row(school_class, academic_year, subgroup) for school_class in classes]
    rows = sort_class_rows(rows, sort)

    teacher_options = User.query.filter_by(role='teacher', is_active=True).order_by(User.username).all()
    class_options = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all()
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
        teacher_options=teacher_options,
        class_options=class_options,
    )


@admin_bp.route('/classes/<int:class_id>')
@login_required
@admin_required
def class_detail(class_id: int):
    academic_year = request.args.get('academic_year', get_current_academic_year())
    school_class = SchoolClass.query.get_or_404(class_id)
    context = get_class_detail_context(school_class, academic_year)
    return render_template('admin/class_detail.html', academic_year=academic_year, **context)


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
                if not username or not password:
                    raise ValueError('Username and password are required.')
                if User.query.filter_by(username=username).first():
                    raise ValueError('That username already exists.')
                user = User(username=username, role='teacher')
                user.set_password(password)
                db.session.add(user)
                flash(f'Created teacher user {username}.', 'success')
            elif action == 'update':
                user = User.query.get_or_404(int(request.form.get('user_id', '0')))
                username = request.form.get(f'username_{user.id}', '').strip()
                password = request.form.get(f'password_{user.id}', '').strip()
                if username and username != user.username:
                    if User.query.filter(User.username == username, User.id != user.id).first():
                        raise ValueError('That username is already in use.')
                    user.username = username
                if password:
                    user.set_password(password)
                db.session.add(user)
                flash(f'Updated {user.username}.', 'success')
            db.session.commit()
            return redirect(url_for('admin.users'))
        except ValueError as exc:
            db.session.rollback()
            flash(f'User changes could not be saved: {exc}', 'danger')

    teachers = User.query.order_by(User.role.desc(), User.username).all()
    classes = SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    return render_template('admin/users.html', teachers=teachers, classes=classes)


@admin_bp.route('/pupils')
@login_required
@admin_required
def pupils():
    pupils = Pupil.query.order_by(Pupil.last_name, Pupil.first_name).all()
    return render_template('admin/pupils.html', pupils=pupils)


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


@admin_bp.route('/sats')
@login_required
@admin_required
def sats():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    year6_classes = SchoolClass.query.filter_by(year_group=6, is_active=True).order_by(SchoolClass.name).all()
    pupils = Pupil.query.join(Pupil.school_class).filter(SchoolClass.year_group == 6, Pupil.is_active.is_(True)).order_by(SchoolClass.name, Pupil.last_name, Pupil.first_name).all()
    rows = []
    for pupil in pupils:
        subjects = {subject: get_sats_subject_summary(SatsResult.query.filter_by(pupil_id=pupil.id, subject=subject, academic_year=academic_year).all()) for subject in SATS_SUBJECTS}
        writing = get_sats_writing_summary(SatsWritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year).all())
        rows.append({'pupil': pupil, 'subjects': subjects, 'writing': writing})
    class_summaries = [build_year6_sats_summary(school_class, academic_year) for school_class in year6_classes]
    return render_template('admin/sats.html', academic_year=academic_year, rows=rows, class_summaries=class_summaries, assessment_points=SATS_ASSESSMENT_POINTS, sats_subjects=SATS_SUBJECTS)


@admin_bp.route('/imports', methods=['GET', 'POST'])
@login_required
@admin_required
def imports():
    if request.method == 'POST':
        import_type = request.form.get('import_type', 'pupils')
        try:
            rows = parse_uploaded_csv(request.files.get('csv_file'))
            if import_type == 'pupils':
                summary = import_pupils(rows)
            elif import_type == 'subject_results':
                summary = import_subject_results(rows)
            else:
                summary = import_writing_results(rows)
            if summary.errors:
                for error in summary.errors[:20]:
                    flash(error, 'warning')
            db.session.commit()
            flash(f'Import finished: created {summary.created}, updated {summary.updated}, skipped {summary.skipped}, errors {len(summary.errors)}.', 'success')
            return redirect(url_for('admin.imports'))
        except CsvImportError as exc:
            db.session.rollback()
            flash(f'Import failed: {exc}', 'danger')

    overview = {'teachers': User.query.filter_by(role='teacher').count(), 'classes': SchoolClass.query.count(), 'pupils': Pupil.query.count()}
    return render_template('admin/imports.html', overview=overview, class_options=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all(), current_year=get_current_academic_year())


@admin_bp.route('/imports/template/<template_type>')
@login_required
@admin_required
def download_import_template(template_type: str):
    template_map = {'pupils', 'subject_results', 'writing_results'}
    if template_type not in template_map:
        flash('Unknown template type.', 'warning')
        return redirect(url_for('admin.imports'))
    csv_text = generate_csv(template_type)
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={template_type}_template.csv'})


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
