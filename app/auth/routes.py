"""Authentication routes."""

from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User
from app.utils import is_demo_mode_enabled

from . import auth_bp
from .forms import ChangePasswordForm, LoginForm


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Log a user into the application."""

    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        credentials_valid = bool(user and user.is_active and user.check_password(form.password.data))
        school_active_or_exec = bool(user and (user.is_executive_admin or user.school is None or user.school.is_active))
        if credentials_valid and school_active_or_exec:
            login_user(user)
            if user.require_password_change:
                flash('Please set a new password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            flash('Welcome back.', 'success')
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc == '':
                return redirect(next_page)
            return redirect(url_for('dashboards.index'))

        if credentials_valid and not school_active_or_exec:
            flash('Your school is inactive. Contact an executive administrator.', 'danger')
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/demo-login')
def demo_login():
    """Shortcut login helpers for demo accounts when demo mode is enabled."""

    if not is_demo_mode_enabled():
        flash('Demo login is not available.', 'warning')
        return redirect(url_for('auth.login'))
    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))

    account = (request.args.get('account') or 'teacher').strip().lower()
    username = 'demo_admin' if account == 'admin' else 'demo_teacher'
    user = User.query.filter_by(username=username, is_active=True).first()
    if not user:
        flash('Demo account is missing. Run seed_demo.py to create demo users.', 'danger')
        return redirect(url_for('auth.login'))
    if not user.is_executive_admin and user.school and not user.school.is_active:
        flash('Demo school is inactive.', 'danger')
        return redirect(url_for('auth.login'))
    login_user(user)
    flash(f'Signed in as {username}.', 'success')
    return redirect(url_for('dashboards.index'))


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""

    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow authenticated users to set their own password."""

    form = ChangePasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.new_password.data)
        current_user.require_password_change = False
        db.session.add(current_user)
        db.session.commit()
        flash('Password updated successfully.', 'success')
        return redirect(url_for('dashboards.index'))
    return render_template('auth/change_password.html', form=form)
