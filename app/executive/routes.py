from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.models import Pupil, School, SchoolClass, User
from app.utils import executive_admin_required

from . import executive_bp

EXPORT_TABLES = [
    'schools',
    'users',
    'school_classes',
    'pupils',
    'subject_results',
    'writing_results',
    'interventions',
    'foundation_results',
    'phonics_scores',
    'times_table_scores',
    'reception_tracker_entries',
    'tracker_mode_settings',
    'sats_exam_tabs',
    'sats_column_settings',
    'sats_column_results',
    'sats_results',
    'sats_writing_results',
]


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', (value or '').lower()).strip('-')
    return slug or 'school'


def _build_export_filename(scope: str, extension: str) -> str:
    date_suffix = datetime.utcnow().strftime('%Y%m%d')
    return f'exec_export_{scope}_{date_suffix}.{extension}'


def _fetch_table_rows(table_name: str, school_id: int | None, schools_by_id: dict[int, School]) -> list[dict]:
    table = db.metadata.tables.get(table_name)
    if table is None:
        return []

    columns = [column.name for column in table.columns]
    select_columns = [name for name in columns if not (table_name == 'users' and name == 'password_hash')]
    if not select_columns:
        return []

    sql = f"SELECT {', '.join(select_columns)} FROM {table_name}"
    params: dict[str, int] = {}
    if school_id is not None and 'school_id' in columns:
        sql += ' WHERE school_id = :school_id'
        params['school_id'] = school_id
    sql += ';'

    result = db.session.execute(text(sql), params)
    rows = [dict(row._mapping) for row in result]

    if 'school_id' in select_columns:
        for row in rows:
            current_school_id = row.get('school_id')
            school = schools_by_id.get(current_school_id)
            row['school_name'] = school.name if school else ''

    if table_name == 'schools':
        for row in rows:
            row['school_name'] = row.get('name', '')

    return rows


def _table_to_csv_bytes(rows: list[dict]) -> bytes:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def _build_zip_export(table_rows: dict[str, list[dict]], scope: str) -> tuple[bytes, str]:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
        for table_name, rows in table_rows.items():
            archive.writestr(f'{table_name}.csv', _table_to_csv_bytes(rows))
    output.seek(0)
    return output.getvalue(), _build_export_filename(scope, 'zip')


def _build_combined_csv_export(table_rows: dict[str, list[dict]], scope: str) -> tuple[bytes, str]:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['table_name', 'column_name', 'value'])

    for table_name, rows in table_rows.items():
        for row in rows:
            for column_name, value in row.items():
                writer.writerow([table_name, column_name, value])

    return output.getvalue().encode('utf-8'), _build_export_filename(scope, 'csv')


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


@executive_bp.route('/users')
@login_required
@executive_admin_required
def users():
    users_list = User.query.join(School, User.school_id == School.id, isouter=True).order_by(User.created_at.desc()).all()
    return render_template('executive/users.html', users=users_list)


@executive_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@executive_admin_required
def reset_user_password(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.is_executive_admin:
        flash('Executive admin passwords cannot be reset here.', 'danger')
        return redirect(url_for('executive.users'))

    password = request.form.get('new_password', '').strip()
    require_change = request.form.get('require_password_change') == 'on'
    if not password:
        flash('A new password is required for reset.', 'danger')
        return redirect(url_for('executive.users'))
    if len(password) < 8:
        flash('New password must be at least 8 characters long.', 'danger')
        return redirect(url_for('executive.users'))

    user.set_password(password)
    user.require_password_change = require_change
    db.session.add(user)
    db.session.commit()
    flash(f'Password reset for {user.username}.', 'success')
    return redirect(url_for('executive.users'))


@executive_bp.route('/export', methods=['GET', 'POST'])
@login_required
@executive_admin_required
def export_data():
    schools_list = School.query.order_by(School.name).all()

    if request.method == 'POST':
        scope = request.form.get('scope', 'all').strip()
        output_format = request.form.get('format', 'zip').strip().lower()
        school_id_raw = request.form.get('school_id', '').strip()

        selected_school: School | None = None
        selected_school_id: int | None = None
        if scope == 'school':
            if not school_id_raw.isdigit():
                flash('Choose a school for school-level export.', 'danger')
                return redirect(url_for('executive.export_data'))
            selected_school_id = int(school_id_raw)
            selected_school = School.query.get_or_404(selected_school_id)

        schools_by_id = {school.id: school for school in schools_list}
        rows_by_table = {
            table_name: _fetch_table_rows(table_name, selected_school_id, schools_by_id)
            for table_name in EXPORT_TABLES
        }

        scope_name = 'all-schools' if selected_school is None else _slugify(selected_school.slug or selected_school.name)
        if output_format == 'csv':
            file_bytes, filename = _build_combined_csv_export(rows_by_table, scope_name)
            mimetype = 'text/csv'
        else:
            file_bytes, filename = _build_zip_export(rows_by_table, scope_name)
            mimetype = 'application/zip'

        return Response(
            file_bytes,
            mimetype=mimetype,
            headers={'Content-Disposition': f'attachment; filename={filename}'},
        )

    return render_template('executive/export.html', schools=schools_list)


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
