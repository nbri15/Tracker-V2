"""Teacher subject placeholder pages."""

from flask import render_template
from flask_login import current_user, login_required

from app.models import Pupil, SchoolClass
from app.utils import get_primary_class_for_user, teacher_or_admin_required

from . import teacher_bp


SUBJECT_META = {
    'maths': {'title': 'Maths', 'placeholder': ['Paper 1', 'Paper 2', 'Combined', 'Band']},
    'reading': {'title': 'Reading', 'placeholder': ['Paper 1', 'Paper 2', 'Combined', 'Band']},
    'spag': {'title': 'SPaG', 'placeholder': ['Paper 1', 'Paper 2', 'Combined', 'Band']},
    'writing': {'title': 'Writing', 'placeholder': ['Autumn Band', 'Spring Band', 'Summer Band', 'Notes']},
}


@teacher_bp.route('/maths')
@login_required
@teacher_or_admin_required
def maths():
    return render_subject_page('maths')


@teacher_bp.route('/reading')
@login_required
@teacher_or_admin_required
def reading():
    return render_subject_page('reading')


@teacher_bp.route('/spag')
@login_required
@teacher_or_admin_required
def spag():
    return render_subject_page('spag')


@teacher_bp.route('/writing')
@login_required
@teacher_or_admin_required
def writing():
    return render_subject_page('writing')


def render_subject_page(subject_key: str):
    """Render a spreadsheet-style subject page for the relevant cohort."""

    meta = SUBJECT_META[subject_key]
    if current_user.is_admin:
        pupils = (
            Pupil.query.join(SchoolClass)
            .filter(Pupil.is_active.is_(True), SchoolClass.is_active.is_(True))
            .order_by(SchoolClass.year_group, Pupil.last_name, Pupil.first_name)
            .all()
        )
        school_class = None
    else:
        school_class = get_primary_class_for_user(current_user)
        pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all() if school_class else []

    return render_template(
        'teacher/subject_placeholder.html',
        page_title=meta['title'],
        subject_key=subject_key,
        school_class=school_class,
        pupils=pupils,
        columns=meta['placeholder'],
    )
