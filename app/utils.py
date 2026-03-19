"""Shared utility helpers and access decorators."""

from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user

from app.models import SchoolClass


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


def teacher_or_admin_required(view_func):
    """Allow teachers and admins to access a route."""

    return role_required('teacher', 'admin')(view_func)


def get_primary_class_for_user(user):
    """Return the first active class assigned to the user, if one exists."""

    if not user.is_authenticated:
        return None
    return (
        SchoolClass.query.filter_by(teacher_id=user.id, is_active=True)
        .order_by(SchoolClass.year_group, SchoolClass.name)
        .first()
    )
