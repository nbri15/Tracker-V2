from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensions import db
from app.models import (
    AcademicYear,
    AssessmentSetting,
    AuditLog,
    FoundationResult,
    GapQuestion,
    GapTemplate,
    GapScore,
    Intervention,
    PhonicsScore,
    Pupil,
    PupilClassHistory,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SatsColumnSetting,
    SatsExamTab,
    SatsResult,
    SatsWritingResult,
    School,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    TimesTableTestColumn,
    PhonicsTestColumn,
    TrackerModeSetting,
    User,
    WritingResult,
)
from app.services.admin_ops import initialise_school_data
from app.utils import executive_admin_required, log_audit_event

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


def _is_last_executive_admin(user: User) -> bool:
    if not user.is_executive_admin:
        return False
    active_count = User.query.filter_by(role='executive_admin', is_active=True).count()
    return active_count <= 1


def _can_delete_user(user: User, actor: User) -> tuple[bool, str | None]:
    if user.id == actor.id:
        return False, 'You cannot delete your own account.'
    if user.is_executive_admin and User.query.filter_by(role='executive_admin').count() <= 1:
        return False, 'You cannot delete the last executive admin.'
    if SchoolClass.query.filter_by(teacher_id=user.id).count() > 0:
        return False, 'User is assigned to one or more classes.'
    if FoundationResult.query.filter_by(updated_by_user_id=user.id).count() > 0:
        return False, 'User has audit history on foundation tracker entries.'
    return True, None


def _school_data_counts(school_id: int) -> dict[str, int]:
    return {
        'users': User.query.filter_by(school_id=school_id).count(),
        'pupils': Pupil.query.filter_by(school_id=school_id).count(),
        'classes': SchoolClass.query.filter_by(school_id=school_id).count(),
        'subject_results': SubjectResult.query.filter_by(school_id=school_id).count(),
        'writing_results': WritingResult.query.filter_by(school_id=school_id).count(),
        'foundation_results': FoundationResult.query.filter_by(school_id=school_id).count(),
        'gap_scores': GapScore.query.filter_by(school_id=school_id).count(),
        'phonics_scores': PhonicsScore.query.filter_by(school_id=school_id).count(),
        'times_table_scores': TimesTableScore.query.filter_by(school_id=school_id).count(),
        'reception_entries': ReceptionTrackerEntry.query.filter_by(school_id=school_id).count(),
        'interventions': Intervention.query.filter_by(school_id=school_id).count(),
        'sats_results': SatsResult.query.filter_by(school_id=school_id).count(),
        'sats_writing_results': SatsWritingResult.query.filter_by(school_id=school_id).count(),
        'sats_column_results': SatsColumnResult.query.filter_by(school_id=school_id).count(),
    }


def _can_delete_school(school: School) -> tuple[bool, str | None]:
    if not school.is_archived:
        return False, 'Archive the school before permanent deletion.'
    return True, None


def _permanently_delete_school_data(school: School) -> None:
    school_id = school.id

    User.query.filter(User.school_id == school_id, User.role != 'executive_admin').delete(synchronize_session=False)

    SubjectResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    WritingResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    Intervention.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    FoundationResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    PhonicsScore.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    TimesTableScore.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    ReceptionTrackerEntry.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SatsColumnResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SatsResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SatsWritingResult.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    GapScore.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    PupilClassHistory.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    Pupil.query.filter_by(school_id=school_id).delete(synchronize_session=False)

    GapQuestion.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    GapTemplate.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    AssessmentSetting.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    PhonicsTestColumn.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    TimesTableTestColumn.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SatsColumnSetting.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SatsExamTab.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    TrackerModeSetting.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    AcademicYear.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    SchoolClass.query.filter_by(school_id=school_id).delete(synchronize_session=False)
    AuditLog.query.filter_by(school_id=school_id).delete(synchronize_session=False)


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
            initialise_school_data(school.id)
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

    show_archived = request.args.get('show_archived') == '1'
    schools_query = School.query
    if not show_archived:
        schools_query = schools_query.filter(School.is_archived.is_(False))
    schools_list = schools_query.order_by(School.name).all()
    school_delete_state = {
        school.id: {'can_delete': can_delete, 'reason': reason}
        for school in schools_list
        for can_delete, reason in [_can_delete_school(school)]
    }
    return render_template('executive/schools.html', schools=schools_list, school_delete_state=school_delete_state, show_archived=show_archived)


@executive_bp.route('/users')
@login_required
@executive_admin_required
def users():
    users_list = User.query.join(School, User.school_id == School.id, isouter=True).order_by(User.created_at.desc()).all()
    user_delete_state = {
        user.id: {'can_delete': can_delete, 'reason': reason}
        for user in users_list
        for can_delete, reason in [_can_delete_user(user, current_user)]
    }
    return render_template('executive/users.html', users=users_list, user_delete_state=user_delete_state, is_last_executive_admin=_is_last_executive_admin)


@executive_bp.route('/users/<int:user_id>/confirm-deactivate')
@login_required
@executive_admin_required
def confirm_deactivate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('executive.users'))
    if user.is_executive_admin and _is_last_executive_admin(user):
        flash('You cannot deactivate the last executive admin.', 'danger')
        return redirect(url_for('executive.users'))
    return render_template('executive/confirm_deactivate_user.html', user=user)


@executive_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@executive_admin_required
def deactivate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('executive.users'))
    if user.is_executive_admin and _is_last_executive_admin(user):
        flash('You cannot deactivate the last executive admin.', 'danger')
        return redirect(url_for('executive.users'))
    if not user.is_active:
        flash(f'{user.username} is already inactive.', 'warning')
        return redirect(url_for('executive.users'))
    user.is_active = False
    db.session.add(user)
    db.session.commit()
    flash(f'{user.username} has been deactivated.', 'success')
    return redirect(url_for('executive.users'))


@executive_bp.route('/users/<int:user_id>/reactivate', methods=['POST'])
@login_required
@executive_admin_required
def reactivate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.is_active:
        flash(f'{user.username} is already active.', 'warning')
        return redirect(url_for('executive.users'))
    user.is_active = True
    db.session.add(user)
    db.session.commit()
    flash(f'{user.username} has been reactivated.', 'success')
    return redirect(url_for('executive.users'))


@executive_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@executive_admin_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    can_delete, reason = _can_delete_user(user, current_user)
    if not can_delete:
        flash(reason or 'User cannot be deleted safely.', 'danger')
        return redirect(url_for('executive.users'))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'{username} has been deleted.', 'success')
    return redirect(url_for('executive.users'))


@executive_bp.route('/schools/<int:school_id>/confirm-deactivate')
@login_required
@executive_admin_required
def confirm_deactivate_school(school_id: int):
    school = School.query.get_or_404(school_id)
    return render_template('executive/confirm_deactivate_school.html', school=school)


@executive_bp.route('/schools/<int:school_id>/deactivate', methods=['POST'])
@login_required
@executive_admin_required
def deactivate_school(school_id: int):
    school = School.query.get_or_404(school_id)
    if school.is_archived:
        flash(f'{school.name} is already archived.', 'warning')
        return redirect(url_for('executive.schools'))
    school.is_active = False
    school.is_archived = True
    school.archived_at = datetime.utcnow()
    school.archived_by_user_id = current_user.id
    school.archive_reason = request.form.get('archive_reason', '').strip() or 'Archived by executive admin'
    db.session.add(school)
    log_audit_event('school_archived', 'school', school.id, school_id=school.id, details=f'reason={school.archive_reason}')
    db.session.commit()
    flash(f'{school.name} has been archived.', 'success')
    return redirect(url_for('executive.schools'))


@executive_bp.route('/schools/<int:school_id>/reactivate', methods=['POST'])
@login_required
@executive_admin_required
def reactivate_school(school_id: int):
    school = School.query.get_or_404(school_id)
    if not school.is_archived:
        flash(f'{school.name} is already active.', 'warning')
        return redirect(url_for('executive.schools'))
    school.is_active = True
    school.is_archived = False
    school.archived_at = None
    school.archived_by_user_id = None
    school.archive_reason = None
    db.session.add(school)
    log_audit_event('school_restored', 'school', school.id, school_id=school.id)
    db.session.commit()
    flash(f'{school.name} has been restored.', 'success')
    return redirect(url_for('executive.schools'))


@executive_bp.route('/schools/<int:school_id>/confirm-delete')
@login_required
@executive_admin_required
def confirm_delete_school(school_id: int):
    school = School.query.get_or_404(school_id)
    can_delete, reason = _can_delete_school(school)
    if not can_delete:
        flash(reason or 'School cannot be deleted safely.', 'danger')
        return redirect(url_for('executive.schools'))
    requires_explicit_confirmation = school.name in {'Barrow School', 'Demo School'}
    return render_template(
        'executive/confirm_delete_school.html',
        school=school,
        requires_explicit_confirmation=requires_explicit_confirmation,
        school_counts=_school_data_counts(school.id),
    )


@executive_bp.route('/schools/<int:school_id>/delete', methods=['POST'])
@login_required
@executive_admin_required
def delete_school(school_id: int):
    school = School.query.get_or_404(school_id)
    can_delete, reason = _can_delete_school(school)
    if not can_delete:
        flash(reason or 'School cannot be deleted safely.', 'danger')
        return redirect(url_for('executive.schools'))
    if request.form.get('confirm_delete_text', '').strip() != 'DELETE SCHOOL':
        flash('Type DELETE SCHOOL to confirm permanent deletion.', 'danger')
        return redirect(url_for('executive.confirm_delete_school', school_id=school.id))
    if school.name in {'Barrow School', 'Demo School'} and request.form.get('confirm_school_name', '').strip() != school.name:
        flash(f'Type "{school.name}" to confirm deleting this protected school.', 'danger')
        return redirect(url_for('executive.confirm_delete_school', school_id=school.id))
    school_name = school.name
    school_id_value = school.id
    _permanently_delete_school_data(school)
    db.session.delete(school)
    log_audit_event('school_permanently_deleted', 'school', school_id_value, school_id=school_id_value, details=f'name={school_name}')
    db.session.commit()
    flash(f'{school_name} has been deleted.', 'success')
    return redirect(url_for('executive.archived_schools'))


@executive_bp.route('/archive/schools')
@login_required
@executive_admin_required
def archived_schools():
    schools_list = School.query.filter(School.is_archived.is_(True)).order_by(School.archived_at.desc(), School.name.asc()).all()
    return render_template('executive/archived_schools.html', schools=schools_list)


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

        target_school_id = selected_school.id if selected_school else None
        target_school_name = selected_school.name if selected_school else 'all-schools'
        log_audit_event('export_downloaded', 'school_export', target_school_id or 0, school_id=target_school_id, details=f'scope={scope};school={target_school_name};format={output_format}')
        db.session.commit()

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


@executive_bp.route('/audit-log')
@login_required
@executive_admin_required
def audit_log():
    records = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template('executive/audit_log.html', records=records)
