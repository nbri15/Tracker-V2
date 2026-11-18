"""Authentication routes."""

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import School, User
from app.services import (
    get_current_academic_year,
    get_school_working_academic_year,
    should_show_academic_year_reminder,
)
from app.security import LoginThrottle, password_problem
from app.utils import is_demo_mode_enabled, safe_redirect_target

from . import auth_bp
from .forms import ChangePasswordForm, LoginForm


def _login_rollover_years(user: User) -> tuple[str, str] | None:
    """Return stored/calendar years for an undismissed September reminder."""
    if not user.is_school_admin or not user.school_id:
        return None
    if not should_show_academic_year_reminder(user.school):
        return None
    working_year = get_school_working_academic_year(user.school_id).name
    calendar_year = get_current_academic_year()
    return working_year, calendar_year


def _login_throttle() -> LoginThrottle:
    """Return this app's login limiter, creating it on first use if the factory did not."""

    throttle = current_app.extensions.get('login_throttle')
    if throttle is None:
        throttle = LoginThrottle(
            max_attempts=current_app.config.get('LOGIN_MAX_ATTEMPTS', 5),
            window_seconds=current_app.config.get('LOGIN_WINDOW_SECONDS', 900),
            max_ip_attempts=current_app.config.get('LOGIN_MAX_ATTEMPTS_PER_IP', 30),
        )
        current_app.extensions['login_throttle'] = throttle
    return throttle


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Log a user into the application."""

    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))

    form = LoginForm()
    if form.validate_on_submit():
        school_code = (form.school_code.data or '').strip().lower()
        identifier = form.username.data.strip()
        throttle = _login_throttle()
        client_ip = request.remote_addr or 'unknown'
        throttle_account = f'{school_code}|{identifier}'
        wait_seconds = throttle.seconds_until_allowed(client_ip, throttle_account)
        if wait_seconds:
            minutes = max(1, (wait_seconds + 59) // 60)
            flash(f'Too many failed sign-in attempts. Please wait about {minutes} minute(s) and try again.', 'danger')
            return render_template('auth/login.html', form=form), 429
        user = None
        if school_code:
            school = School.query.filter(School.slug == school_code).first()
            if school:
                user = User.query.filter(
                    User.school_id == school.id,
                    User.username.ilike(identifier),
                ).first()
        else:
            # School accounts must always be resolved inside the supplied school.
            # Only platform-level executives have a code-free login path.
            user = User.query.filter(
                User.role == 'executive_admin',
                User.username.ilike(identifier),
            ).first()
        credentials_valid = bool(user and user.is_active and user.check_password(form.password.data))
        school_active_or_exec = bool(user and (user.is_executive_admin or user.school is None or (user.school.is_active and not user.school.is_archived)))
        if credentials_valid and school_active_or_exec:
            throttle.record_success(client_ip, throttle_account)
            session.pop('selected_academic_year_id', None)
            login_user(user)
            session.permanent = True  # applies the idle timeout (PERMANENT_SESSION_LIFETIME)
            if user.require_password_change:
                flash('Please set a new password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            rollover_years = _login_rollover_years(user)
            if rollover_years:
                working_year, calendar_year = rollover_years
                flash(
                    f"It's September {calendar_year.split('/')[0]} and your school is currently set to "
                    f'{working_year}. Would you like to review the academic-year rollover?',
                    'warning',
                )
                return redirect(url_for('admin.promotion', rollover_prompt='1'))
            flash('Welcome back.', 'success')
            return redirect(safe_redirect_target(request.args.get('next'), url_for('dashboards.index')))

        if not credentials_valid:
            throttle.record_failure(client_ip, throttle_account)
        if credentials_valid and not school_active_or_exec:
            flash('Your school is inactive. Contact an executive administrator.', 'danger')
        else:
            flash('Invalid school code/username/password. School accounts must include their school code.', 'danger')

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
    demo_school = School.query.filter_by(slug='demo-school').first()
    user_query = User.query.filter(User.username.ilike(username), User.is_active.is_(True))
    if demo_school:
        user_query = user_query.filter(User.school_id == demo_school.id)
    user = user_query.first()
    if not user:
        flash('Demo account is missing. Run seed_demo.py to create demo users.', 'danger')
        return redirect(url_for('auth.login'))
    if not user.is_executive_admin and user.school and (not user.school.is_active or user.school.is_archived):
        flash('Demo school is inactive.', 'danger')
        return redirect(url_for('auth.login'))
    login_user(user)
    session.permanent = True
    session.pop('selected_academic_year_id', None)
    flash(f'Signed in as {username}.', 'success')
    return redirect(url_for('dashboards.index'))


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""

    logout_user()
    session.pop('selected_academic_year_id', None)
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow authenticated users to set their own password."""

    form = ChangePasswordForm()
    if form.validate_on_submit():
        problem = password_problem(form.new_password.data, current_user.username)
        if problem:
            form.new_password.errors.append(problem)
            return render_template('auth/change_password.html', form=form)
        current_user.set_password(form.new_password.data)
        current_user.require_password_change = False
        db.session.add(current_user)
        db.session.commit()
        flash('Password updated successfully.', 'success')
        return redirect(url_for('dashboards.index'))
    return render_template('auth/change_password.html', form=form)
