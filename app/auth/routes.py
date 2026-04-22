"""Authentication routes."""

from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User

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
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user)
            if user.require_password_change:
                flash('Please set a new password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            flash('Welcome back.', 'success')
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc == '':
                return redirect(next_page)
            return redirect(url_for('dashboards.index'))

        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html', form=form)


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
