"""Authentication routes."""

from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.models import User

from . import auth_bp
from .forms import LoginForm


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
