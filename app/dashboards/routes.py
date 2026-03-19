"""Dashboard routing for role-aware landing pages."""

from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Pupil, SchoolClass, User
from app.services import (
    CLASS_SORT_OPTIONS,
    build_class_overview_row,
    build_dashboard_summary,
    build_subject_overview_cards,
    get_current_academic_year,
)
from app.utils import admin_required, get_primary_class_for_user, teacher_required

from . import dashboards_bp


@dashboards_bp.route('/')
def home():
    """Public root route redirects to the appropriate dashboard."""

    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))
    return redirect(url_for('auth.login'))


@dashboards_bp.route('/dashboard')
@login_required
def index():
    """Send users to their role-specific dashboard."""

    if current_user.is_admin:
        return redirect(url_for('dashboards.admin_dashboard'))
    return redirect(url_for('dashboards.teacher_dashboard'))


@dashboards_bp.route('/dashboard/teacher')
@login_required
@teacher_required
def teacher_dashboard():
    """Teacher-facing dashboard with real class assessment summaries."""

    school_class = get_primary_class_for_user(current_user)
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all() if school_class else []
    academic_year = get_current_academic_year()
    summary_rows = build_dashboard_summary(school_class.id if school_class else None, academic_year)

    context = {
        'school_class': school_class,
        'pupil_count': len(pupils),
        'academic_year': academic_year,
        'summary_rows': summary_rows,
        'chart_cards': summary_rows,
    }
    return render_template('dashboards/teacher_dashboard.html', **context)


@dashboards_bp.route('/dashboard/admin')
@login_required
@admin_required
def admin_dashboard():
    """Admin-facing dashboard with class overview summaries and filters."""

    academic_year = request.args.get('academic_year', get_current_academic_year())
    filter_year_group = request.args.get('year_group', '').strip()
    filter_teacher = request.args.get('teacher_id', '').strip()
    filter_class = request.args.get('class_id', '').strip()
    sort = request.args.get('sort', 'year_group')

    query = SchoolClass.query.filter_by(is_active=True)
    if filter_year_group:
        query = query.filter(SchoolClass.year_group == int(filter_year_group))
    if filter_teacher:
        query = query.filter(SchoolClass.teacher_id == int(filter_teacher))
    if filter_class:
        query = query.filter(SchoolClass.id == int(filter_class))

    classes = query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    class_rows = [build_class_overview_row(school_class, academic_year) for school_class in classes]

    if sort == 'class_name':
        class_rows.sort(key=lambda row: (row['class_name'].lower(), row['year_group']))
    elif sort == 'pupil_count_desc':
        class_rows.sort(key=lambda row: (-row['pupil_count'], row['class_name'].lower()))
    elif sort == 'pupil_count_asc':
        class_rows.sort(key=lambda row: (row['pupil_count'], row['class_name'].lower()))
    else:
        class_rows.sort(key=lambda row: (row['year_group'], row['class_name'].lower()))

    subject_cards = build_subject_overview_cards(class_rows)
    teacher_options = User.query.filter_by(role='teacher', is_active=True).order_by(User.username).all()
    class_options = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.year_group, SchoolClass.name).all()

    context = {
        'academic_year': academic_year,
        'total_pupils': Pupil.query.filter_by(is_active=True).count(),
        'total_classes': SchoolClass.query.filter_by(is_active=True).count(),
        'teacher_count': User.query.filter_by(role='teacher', is_active=True).count(),
        'filtered_class_count': len(class_rows),
        'class_rows': class_rows,
        'subject_cards': subject_cards,
        'filter_year_group': filter_year_group,
        'filter_teacher': filter_teacher,
        'filter_class': filter_class,
        'sort': sort,
        'sort_options': CLASS_SORT_OPTIONS,
        'teacher_options': teacher_options,
        'class_options': class_options,
    }
    return render_template('dashboards/admin_dashboard.html', **context)
