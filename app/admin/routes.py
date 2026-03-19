"""Admin placeholder routes for school setup and management."""

from flask import render_template
from flask_login import login_required

from app.models import AssessmentSetting, Pupil, SchoolClass, User
from app.utils import admin_required

from . import admin_bp


@admin_bp.route('/classes')
@login_required
@admin_required
def classes():
    """List available classes and their teacher assignments."""

    classes = SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    return render_template('admin/classes.html', classes=classes)


@admin_bp.route('/pupils')
@login_required
@admin_required
def pupils():
    """Display a basic pupil list placeholder."""

    pupils = Pupil.query.order_by(Pupil.last_name, Pupil.first_name).all()
    return render_template('admin/pupils.html', pupils=pupils)


@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    """Display assessment settings scaffold data."""

    settings = AssessmentSetting.query.order_by(
        AssessmentSetting.year_group,
        AssessmentSetting.subject,
        AssessmentSetting.term,
    ).all()
    return render_template('admin/settings.html', settings=settings)


@admin_bp.route('/imports')
@login_required
@admin_required
def imports():
    """Placeholder for future CSV import/export tooling."""

    overview = {
        'teachers': User.query.filter_by(role='teacher').count(),
        'classes': SchoolClass.query.count(),
        'pupils': Pupil.query.count(),
    }
    return render_template('admin/imports.html', overview=overview)
