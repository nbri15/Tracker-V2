"""Dashboard routing for role-aware landing pages."""

from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Intervention, Pupil, SchoolClass, User
from app.services import (
    BOOLEAN_FILTER_CHOICES,
    CLASS_SORT_OPTIONS,
    SUBGROUP_FILTERS,
    build_admin_pupil_filter_state,
    build_class_overview_row,
    build_dashboard_summary,
    build_subject_overview_cards,
    build_year6_sats_overview,
    get_current_academic_year,
    get_gender_filter_options,
    get_tracker_mode,
    get_tracker_mode_label,
    sort_class_rows,
)
from app.utils import (
    admin_required,
    demo_filter_classes,
    demo_filter_pupils,
    get_primary_class_for_user,
    school_scoped_query,
    get_year_group_class_for_user,
    teacher_required,
)

from . import dashboards_bp


@dashboards_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))
    return render_template('public_home.html')


@dashboards_bp.route('/dashboard')
@login_required
def index():
    if current_user.is_executive_admin:
        return redirect(url_for('executive.schools'))
    if current_user.can_manage_school:
        return redirect(url_for('dashboards.admin_dashboard'))
    return redirect(url_for('dashboards.teacher_dashboard'))


@dashboards_bp.route('/dashboard/teacher')
@login_required
@teacher_required
def teacher_dashboard():
    school_class = get_primary_class_for_user(current_user)
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all() if school_class else []
    academic_year = get_current_academic_year()
    summary_rows = build_dashboard_summary(school_class.id if school_class else None, academic_year)
    active_interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(
            Intervention.is_active.is_(True),
            Intervention.academic_year == academic_year,
            Pupil.class_id == school_class.id,
            Pupil.is_active.is_(True),
            Pupil.is_demo.is_(school_class.is_demo),
            Intervention.is_demo.is_(school_class.is_demo),
        )
        .order_by(Pupil.last_name, Pupil.first_name)
        .all()
        if school_class
        else []
    )

    context = {
        'school_class': school_class,
        'has_year6_sats_access': get_year_group_class_for_user(current_user, 6) is not None,
        'pupil_count': len(pupils),
        'academic_year': academic_year,
        'summary_rows': summary_rows,
        'chart_cards': summary_rows,
        'active_interventions': active_interventions,
        'tracker_mode': get_tracker_mode(school_class.year_group) if school_class else 'normal',
        'tracker_mode_label': get_tracker_mode_label(school_class.year_group) if school_class else 'Usual tracker',
    }
    return render_template('dashboards/teacher_dashboard.html', **context)


@dashboards_bp.route('/dashboard/admin')
@login_required
@admin_required
def admin_dashboard():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    filter_year_group = request.args.get('year_group', '').strip()
    filter_teacher = request.args.get('teacher_id', '').strip()
    filter_class = request.args.get('class_id', '').strip()
    subgroup = request.args.get('subgroup', 'all').strip() or 'all'
    sort = request.args.get('sort', 'year_group')
    pupil_filters = build_admin_pupil_filter_state(request.args)

    query = demo_filter_classes(SchoolClass.query.filter_by(is_active=True))
    if filter_year_group:
        query = query.filter(SchoolClass.year_group == int(filter_year_group))
    if filter_teacher:
        query = query.filter(SchoolClass.teacher_id == int(filter_teacher))
    if filter_class:
        query = query.filter(SchoolClass.id == int(filter_class))

    classes = query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    class_rows = [build_class_overview_row(school_class, academic_year, subgroup, pupil_filters) for school_class in classes]
    class_rows = sort_class_rows(class_rows, sort)
    subject_cards = build_subject_overview_cards(class_rows)
    teacher_options = school_scoped_query(User, User.query.filter_by(role='teacher', is_active=True, is_demo=current_user.is_demo)).order_by(User.username).all()
    class_options = demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).order_by(SchoolClass.year_group, SchoolClass.name).all()
    year6_overview = build_year6_sats_overview(academic_year)

    context = {
        'academic_year': academic_year,
        'total_pupils': demo_filter_pupils(Pupil.query.filter_by(is_active=True)).count(),
        'total_classes': demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).count(),
        'teacher_count': school_scoped_query(User, User.query.filter_by(role='teacher', is_active=True, is_demo=current_user.is_demo)).count(),
        'filtered_pupil_total': sum(row['pupil_count'] for row in class_rows),
        'filtered_class_count': len(class_rows),
        'class_rows': class_rows,
        'subject_cards': subject_cards,
        'filter_year_group': filter_year_group,
        'filter_teacher': filter_teacher,
        'filter_class': filter_class,
        'subgroup': subgroup,
        'pupil_filters': pupil_filters,
        'subgroup_filters': SUBGROUP_FILTERS,
        'boolean_filter_choices': BOOLEAN_FILTER_CHOICES,
        'gender_options': get_gender_filter_options(class_id=int(filter_class)) if filter_class else get_gender_filter_options(),
        'sort': sort,
        'sort_options': CLASS_SORT_OPTIONS,
        'teacher_options': teacher_options,
        'class_options': class_options,
        'year6_overview': year6_overview,
        'year6_tracker_mode_label': get_tracker_mode_label(6),
    }
    return render_template('dashboards/admin_dashboard.html', **context)
