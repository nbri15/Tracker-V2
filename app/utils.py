"""Shared utility helpers and access decorators."""

from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, url_for
from flask_login import current_user

from app.models import Pupil, SchoolClass


def role_required(*roles):
    """Restrict a route to one or more application roles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('You do not have permission to view that page.', 'danger')
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator


def admin_required(view_func):
    """Require the current user to be a school admin or executive admin."""

    return role_required('school_admin', 'executive_admin', 'admin')(view_func)


def executive_admin_required(view_func):
    """Require executive admin role."""

    return role_required('executive_admin')(view_func)


def teacher_required(view_func):
    """Require the current user to be a teacher."""

    return role_required('teacher')(view_func)


def teacher_or_admin_required(view_func):
    """Allow teachers and admin roles to access a route."""

    return role_required('teacher', 'school_admin', 'executive_admin', 'admin')(view_func)


def current_school_id() -> int | None:
    """Return selected/current school id for the request."""

    if not getattr(current_user, 'is_authenticated', False):
        return None
    if getattr(current_user, 'is_executive_admin', False):
        selected = request.args.get('school_id') or request.form.get('school_id') or getattr(g, 'selected_school_id', None)
        if selected and str(selected).isdigit():
            return int(selected)
        return None
    return getattr(current_user, 'school_id', None)


def user_can_access_school(user, school_id: int | None) -> bool:
    """Return whether user can access a school boundary."""

    if school_id is None:
        return bool(getattr(user, 'is_executive_admin', False))
    return bool(getattr(user, 'is_executive_admin', False) or getattr(user, 'school_id', None) == school_id)


def require_same_school(obj) -> None:
    """Abort if object belongs to another school."""

    school_id = getattr(obj, 'school_id', None)
    if not user_can_access_school(current_user, school_id):
        abort(403)


def school_scoped_query(model, query=None):
    """Apply school scoping to a model query that has a school_id column."""

    scoped = query if query is not None else model.query
    if not getattr(current_user, 'is_authenticated', False):
        return scoped
    if hasattr(model, 'school_id'):
        school_id = current_school_id()
        if school_id is not None:
            return scoped.filter(model.school_id == school_id)
        if not getattr(current_user, 'is_executive_admin', False):
            return scoped.filter(model.school_id == getattr(current_user, 'school_id', None))
    return scoped


def get_primary_class_for_user(user):
    if not user.is_authenticated:
        return None
    return (
        school_scoped_query(SchoolClass, SchoolClass.query.filter_by(teacher_id=user.id, is_active=True))
        .order_by(SchoolClass.year_group, SchoolClass.name)
        .first()
    )


def get_year_group_class_for_user(user, year_group: int):
    if not user.is_authenticated:
        return None
    return (
        school_scoped_query(SchoolClass, SchoolClass.query.filter_by(teacher_id=user.id, is_active=True, year_group=year_group))
        .order_by(SchoolClass.name)
        .first()
    )


def is_demo_user(user=None) -> bool:
    target_user = user if user is not None else current_user
    return bool(getattr(target_user, 'is_authenticated', False) and getattr(target_user, 'is_demo', False))


def demo_filter_classes(query):
    return school_scoped_query(SchoolClass, query).filter(SchoolClass.is_demo.is_(is_demo_user())) if getattr(current_user, 'is_authenticated', False) else query


def demo_filter_pupils(query):
    return school_scoped_query(Pupil, query).filter(Pupil.is_demo.is_(is_demo_user())) if getattr(current_user, 'is_authenticated', False) else query


def is_demo_mode_enabled() -> bool:
    return bool(current_app.config.get('DEMO_MODE', False))
