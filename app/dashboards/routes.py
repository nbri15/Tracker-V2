"""Dashboard routing for role-aware landing pages."""

from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models import Pupil, SchoolClass, User
from app.services import build_dashboard_summary, get_current_academic_year
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
    """Admin-facing dashboard with whole-school placeholder analytics."""

    context = {
        'total_pupils': Pupil.query.filter_by(is_active=True).count(),
        'total_classes': SchoolClass.query.filter_by(is_active=True).count(),
        'teacher_count': User.query.filter_by(role='teacher', is_active=True).count(),
    }
    return render_template('dashboards/admin_dashboard.html', **context)
