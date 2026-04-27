from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Pupil, School, SchoolClass, User
from app.utils import executive_admin_required

from . import executive_bp


@executive_bp.route('/schools', methods=['GET', 'POST'])
@login_required
@executive_admin_required
def schools():
    if request.method == 'POST':
        action = request.form.get('action', 'create')
        if action == 'create':
            school = School(
                name=request.form.get('name', '').strip(),
                slug=request.form.get('slug', '').strip().lower(),
                is_active=request.form.get('is_active') == 'on',
                is_demo=request.form.get('is_demo') == 'on',
            )
            db.session.add(school)
            db.session.commit()
            flash(f'Created school {school.name}.', 'success')
        elif action == 'update':
            school = School.query.get_or_404(int(request.form.get('school_id', '0')))
            school.name = request.form.get(f'name_{school.id}', school.name).strip()
            school.slug = request.form.get(f'slug_{school.id}', school.slug).strip().lower()
            school.is_active = request.form.get(f'is_active_{school.id}') == 'on'
            school.is_demo = request.form.get(f'is_demo_{school.id}') == 'on'
            db.session.add(school)
            db.session.commit()
            flash(f'Updated {school.name}.', 'success')
        return redirect(url_for('executive.schools'))

    schools_list = School.query.order_by(School.name).all()
    return render_template('executive/schools.html', schools=schools_list)


@executive_bp.route('/schools/<int:school_id>')
@login_required
@executive_admin_required
def school_detail(school_id: int):
    school = School.query.get_or_404(school_id)
    users = User.query.filter_by(school_id=school.id).order_by(User.role.desc(), User.username).all()
    context = {
        'school': school,
        'users_count': len(users),
        'classes_count': SchoolClass.query.filter_by(school_id=school.id).count(),
        'pupils_count': Pupil.query.filter_by(school_id=school.id).count(),
        'users': users,
    }
    return render_template('executive/school_detail.html', **context)


@executive_bp.route('/schools/<int:school_id>/create-admin', methods=['POST'])
@login_required
@executive_admin_required
def create_school_admin(school_id: int):
    school = School.query.get_or_404(school_id)
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('executive.school_detail', school_id=school.id))
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
        return redirect(url_for('executive.school_detail', school_id=school.id))

    user = User(
        username=username,
        role='school_admin',
        legacy_is_admin=True,
        school_id=school.id,
        is_demo=school.is_demo,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'Created school admin {username} for {school.name}.', 'success')
    return redirect(url_for('executive.school_detail', school_id=school.id))


@executive_bp.route('/schools/<int:school_id>/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@executive_admin_required
def reset_school_user_password(school_id: int, user_id: int):
    school = School.query.get_or_404(school_id)
    user = User.query.filter_by(id=user_id, school_id=school.id).first_or_404()
    if user.is_executive_admin:
        flash('Executive admin passwords cannot be reset from school management.', 'danger')
        return redirect(url_for('executive.school_detail', school_id=school.id))

    password = request.form.get('new_password', '').strip()
    require_change = request.form.get('require_password_change') == 'on'
    if not password:
        flash('A new password is required for reset.', 'danger')
        return redirect(url_for('executive.school_detail', school_id=school.id))
    if len(password) < 8:
        flash('New password must be at least 8 characters long.', 'danger')
        return redirect(url_for('executive.school_detail', school_id=school.id))

    user.set_password(password)
    user.require_password_change = require_change
    db.session.add(user)
    db.session.commit()
    flash(f'Password reset for {user.username} at {school.name}.', 'success')
    return redirect(url_for('executive.school_detail', school_id=school.id))
