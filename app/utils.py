"""Shared utility helpers and access decorators."""

from functools import wraps

from flask import abort, current_app, flash, redirect, url_for
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
    """Require the current user to be an administrator."""

    return role_required('admin')(view_func)


def teacher_required(view_func):
    """Require the current user to be a teacher."""

    return role_required('teacher')(view_func)


def teacher_or_admin_required(view_func):
    """Allow teachers and admins to access a route."""

    return role_required('teacher', 'admin')(view_func)


def get_primary_class_for_user(user):
    """Return the first active class assigned to the user, if one exists."""

    if not user.is_authenticated:
        return None
    return (
        demo_filter_classes(SchoolClass.query.filter_by(teacher_id=user.id, is_active=True))
        .order_by(SchoolClass.year_group, SchoolClass.name)
        .first()
    )


def get_year_group_class_for_user(user, year_group: int):
    """Return the first active class in a specific year group for the user."""

    if not user.is_authenticated:
        return None
    return (
        demo_filter_classes(SchoolClass.query.filter_by(teacher_id=user.id, is_active=True, year_group=year_group))
        .order_by(SchoolClass.name)
        .first()
    )


def is_demo_user(user=None) -> bool:
    """Return whether a user should be treated as a demo-scoped account."""

    target_user = user if user is not None else current_user
    return bool(getattr(target_user, 'is_authenticated', False) and getattr(target_user, 'is_demo', False))


def demo_filter_classes(query):
    """Apply class-level demo segregation for the current user."""

    if not getattr(current_user, 'is_authenticated', False):
        return query
    return query.filter(SchoolClass.is_demo.is_(is_demo_user()))


def demo_filter_pupils(query):
    """Apply pupil-level demo segregation for the current user."""

    if not getattr(current_user, 'is_authenticated', False):
        return query
    return query.filter(Pupil.is_demo.is_(is_demo_user()))


def is_demo_mode_enabled() -> bool:
    """Return whether the app is running in demo mode."""

    return bool(current_app.config.get('DEMO_MODE', False))
