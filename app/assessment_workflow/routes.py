"""Review first, confirm once: assessment setup and uploads."""
from __future__ import annotations
import base64
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from flask import abort, current_app, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models import AcademicYear, AssessmentReview, Pupil, SchoolClass, SubjectResult
from app.utils import admin_required, current_school_id, get_primary_class_for_user, log_audit_event, teacher_required, teacher_or_admin_required
from app.services.assessments import CORE_SUBJECTS, TERMS, AssessmentValidationError, CsvImportError, get_selected_academic_year, get_subject_setting, get_school_working_academic_year, validate_setting_payload
from app.services.assessment_reliability import CONFIG_FIELDS, apply_setup, assessment_history, configuration_values, lock_school, raw_boundary, school_fingerprint, setup_impact
from app.services.assessment_imports import class_pupils, parse_csv_bytes, process_import, read_upload, simulate_import
from . import assessment_bp


def require_school():
    school_id = current_school_id()
    if school_id is None:
        abort(403)
    return school_id


def selected_upload_year():
    raw_id = request.form.get('academic_year_id')
    year = db.session.get(AcademicYear, int(raw_id)) if raw_id and raw_id.isdigit() else None
    return year.name if year else get_school_working_academic_year(require_school()).name


def back_url(review):
    payload = review.payload
    if review.kind == 'setup':
        return url_for('assessment_workflow.setup', academic_year=payload['academic_year'], year_group=payload['year_group'], subject=payload['subject'], term=payload['term'], school_id=review.school_id)
    if review.kind == 'subject':
        return url_for('teacher.' + payload['subject'], academic_year=payload['academic_year'], term=payload['term'])
    return url_for('admin.imports', school_id=review.school_id)


def stage(kind, payload, report):
    # Review files are temporary; the durable history is in AuditLog.
    AssessmentReview.query.filter(AssessmentReview.school_id == require_school(), AssessmentReview.created_at < datetime.now(timezone.utc) - timedelta(days=1)).delete(synchronize_session=False)
    review = AssessmentReview(school_id=require_school(), user_id=current_user.id, kind=kind, payload=payload, report=report, baseline=school_fingerprint(require_school()))
    db.session.add(review)
    db.session.commit()
    return redirect(url_for('assessment_workflow.review', review_id=review.id, school_id=review.school_id))


def load_review(review_id, *, lock=False):
    statement = select(AssessmentReview).where(AssessmentReview.id == review_id, AssessmentReview.school_id == require_school(), AssessmentReview.user_id == current_user.id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    review = db.session.execute(statement).scalar_one_or_none()
    if not review:
        abort(404)
    if review.kind == 'subject':
        school_class = get_primary_class_for_user(current_user)
        if not current_user.is_teacher or not school_class or school_class.id != review.payload['class_id']:
            abort(403)
    elif not current_user.can_manage_school and not current_user.is_executive_admin:
        abort(403)
    return review


@assessment_bp.route('/admin/assessments/setup', methods=['GET', 'POST'])
@login_required
@admin_required
def setup():
    school_id = require_school()
    selected_year = get_selected_academic_year()
    academic_year = selected_year.name
    try:
        group = int(request.values.get('year_group', '5'))
        subject = request.values.get('subject', 'maths')
        term = request.values.get('term', 'autumn')
        current = get_subject_setting(group, subject, term, academic_year, school_id=school_id)
    except (ValueError, AssessmentValidationError):
        abort(400)
    if request.method == 'POST':
        try:
            expected = float(request.form.get('below_are_threshold_percent', ''))
            proposed = validate_setting_payload({
                'paper_1_name': request.form.get('paper_1_name', '').strip(),
                'paper_1_max': int(request.form.get('paper_1_max', '')),
                'paper_2_name': request.form.get('paper_2_name', '').strip(),
                'paper_2_max': int(request.form.get('paper_2_max', '')),
                'combined_max': None,
                'below_are_threshold_percent': expected,
                'on_track_threshold_percent': expected,
                'exceeding_threshold_percent': float(request.form.get('exceeding_threshold_percent', '')),
            })
            report = setup_impact(school_id, academic_year, group, subject, term, proposed)
            payload = {'school_id': school_id, 'academic_year': academic_year, 'year_group': group, 'subject': subject, 'term': term, 'proposed': proposed, 'current': configuration_values(current)}
            return stage('setup', payload, report)
        except (ValueError, AssessmentValidationError) as exc:
            flash(f'Setup could not be reviewed: {exc}', 'danger')
    return render_template('assessment_setup.html', setting=current, academic_year=academic_year, selected_year=selected_year, years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(), group=group, subject=subject, term=term, subjects=CORE_SUBJECTS, terms=TERMS, at_boundary=raw_boundary(current, current.below_are_threshold_percent) if current.combined_max and current.combined_max > 0 else None, gds_boundary=raw_boundary(current, current.exceeding_threshold_percent) if current.combined_max and current.combined_max > 0 else None, history=assessment_history(school_id))


@assessment_bp.route('/assessments/review/<review_id>', methods=['GET', 'POST'])
@login_required
@teacher_or_admin_required
def review(review_id):
    record = load_review(review_id)
    expires = record.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=30)
    expired = datetime.now(timezone.utc) > expires
    if request.method == 'POST':
        if request.form.get('action') == 'cancel':
            target = back_url(record)
            db.session.delete(record)
            db.session.commit()
            return redirect(target)
        try:
            lock_school(record.school_id)
            record = load_review(review_id, lock=True)
            if datetime.now(timezone.utc) > record.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=30) or record.confirmed_at:
                raise CsvImportError('This review has expired or already been applied. Upload/review again.')
            if record.report.get('errors'):
                raise CsvImportError('Fix the errors in this preview and upload/review again.')
            if school_fingerprint(record.school_id) != record.baseline:
                raise CsvImportError('School data changed after this preview. Review again so you can see the latest impact.')
            if record.kind == 'setup':
                payload = record.payload
                report = setup_impact(payload['school_id'], payload['academic_year'], payload['year_group'], payload['subject'], payload['term'], payload['proposed'])
                if report['errors']:
                    raise CsvImportError('The proposed setup is incompatible with saved scores. Review again.')
                count = apply_setup(payload)
                message = f'Assessment setup applied. {count} results recalculated for {payload["academic_year"]} only.'
            else:
                report = process_import(record.kind, record.payload)
                if report.get('errors'):
                    raise CsvImportError('Import validation changed. No results were saved. Upload again.')
                from app.services.interventions import sync_auto_interventions
                from app.services.assessment_reliability import assessment_health
                payload = record.payload
                if record.kind == 'subject':
                    school_class, pupils = class_pupils(payload)
                    setting = get_subject_setting(school_class.year_group, payload['subject'], payload['term'], payload['academic_year'], school_id=record.school_id)
                    if payload['academic_year'] == get_school_working_academic_year(record.school_id).name:
                        sync_auto_interventions(school_class, payload['subject'], payload['term'], payload['academic_year'], setting.below_are_threshold_percent)
                else:
                    # Re-sync only current-year scopes, preserving historical interventions.
                    if payload['academic_year'] == get_school_working_academic_year(record.school_id).name:
                        for school_class in SchoolClass.query.filter_by(school_id=record.school_id, is_active=True).all():
                            if school_class.year_group == 0:
                                continue
                            for subject in CORE_SUBJECTS:
                                for term, _ in TERMS:
                                    setting = get_subject_setting(school_class.year_group, subject, term, payload['academic_year'], school_id=record.school_id)
                                    sync_auto_interventions(school_class, subject, term, payload['academic_year'], setting.below_are_threshold_percent)
                log_audit_event('assessment_results_imported', 'school', record.school_id, school_id=record.school_id, details=json.dumps({'kind': record.kind, 'academic_year': payload['academic_year'], 'added': report.get('added', 0), 'updated': report.get('changed_results', report.get('updated', 0)), 'skipped': report.get('skipped', 0), 'review_id': record.id}))
                message = f'Import complete: {report.get("added", 0)} results added; {report.get("changed_results", report.get("updated", 0))} updated; 0 failed; {report.get("skipped", 0)} protected/blank rows skipped.'
                if 'without_score' in report:
                    message += f' {report["without_score"]} pupils remain without a complete score.'
            record.confirmed_at = datetime.now(timezone.utc)
            record.report = report
            # Purge uploaded pupil/file payload after success; retain summary audit.
            record.payload = {key: value for key, value in record.payload.items() if key not in {'rows', 'workbook'}}
            db.session.commit()
            flash(message, 'success')
            return redirect(back_url(record))
        except (CsvImportError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Reviewed assessment import failed')
            flash('The database could not save this import. No pupil results were saved. Review again and retry.', 'danger')
    return render_template('assessment_review.html', review=record, report=record.report, back=back_url(record), expired=expired)


def upload_admin_csv():
    school_id = require_school()
    kind = request.form.get('import_type', 'combined')
    try:
        rows = parse_csv_bytes(read_upload(request.files.get('csv_file'), '.csv'))
        year = selected_upload_year()
        for row in rows:
            if not (row.get('academic_year') or '').strip():
                row['academic_year'] = year
        payload = {'school_id': school_id, 'academic_year': year, 'rows': rows}
        report = simulate_import(kind, payload)
        return stage(kind, payload, report)
    except (ValueError, CsvImportError, SQLAlchemyError) as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, ValueError) else 'The file could not be validated. No pupil data was saved.', 'danger')
        return redirect(url_for('admin.imports', school_id=school_id))


def upload_workbook():
    school_id = require_school()
    try:
        data = read_upload(request.files.get('workbook_file'), '.xlsx')
        payload = {'school_id': school_id, 'academic_year': selected_upload_year(), 'workbook': base64.b64encode(data).decode()}
        report = simulate_import('workbook', payload)
        return stage('workbook', payload, report)
    except (ValueError, CsvImportError, SQLAlchemyError) as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, ValueError) else 'The workbook could not be validated. No pupil data was saved.', 'danger')
        return redirect(url_for('admin.imports', school_id=school_id))


@assessment_bp.route('/teacher/<subject>/upload', methods=['POST'])
@login_required
@teacher_required
def upload_subject(subject):
    school_id = require_school()
    school_class = get_primary_class_for_user(current_user)
    if not school_class or subject not in CORE_SUBJECTS:
        abort(404)
    selected_year = get_selected_academic_year()
    payload = {'school_id': school_id, 'class_id': school_class.id, 'academic_year': selected_year.name, 'subject': subject, 'term': request.form.get('term', 'autumn'), 'replace_existing': request.form.get('replace_existing') == 'yes'}
    try:
        payload['rows'] = parse_csv_bytes(read_upload(request.files.get('csv_file'), '.csv'))
        report = simulate_import('subject', payload)
        return stage('subject', payload, report)
    except (ValueError, CsvImportError, SQLAlchemyError) as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, ValueError) else 'The file could not be validated. No scores were saved.', 'danger')
        return redirect(url_for('teacher.' + subject, academic_year=selected_year.name, term=payload['term']))


@assessment_bp.route('/teacher/<subject>/import-template.csv')
@login_required
@teacher_required
def subject_template(subject):
    school_class = get_primary_class_for_user(current_user)
    if not school_class or subject not in CORE_SUBJECTS:
        abort(404)
    year = get_selected_academic_year().name
    payload = {'school_id': require_school(), 'class_id': school_class.id, 'academic_year': year}
    _, pupils = class_pupils(payload)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['pupil_id', 'pupil', 'class_name', 'academic_year', 'paper_1_score', 'paper_2_score'])
    for pupil in pupils:
        writer.writerow([pupil.id, pupil.full_name, school_class.name, year, '', ''])
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={subject}-scores.csv'})


@assessment_bp.route('/teacher/<subject>/calculate', methods=['POST'])
@login_required
@teacher_required
def calculate_cells(subject):
    from app.services.assessment_reliability import setting_for_result, cohort_year_group
    from app.services.assessment_imports import parse_score
    from app.services.assessments import compute_subject_result_values, resolve_subject_band_label
    school_class = get_primary_class_for_user(current_user)
    if not school_class or subject not in CORE_SUBJECTS:
        abort(404)
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get('rows'), list) or len(data['rows']) > 500:
        abort(400)
    year = get_selected_academic_year(raw_academic_year=data.get('academic_year')).name
    term = data.get('term', 'autumn')
    if term not in dict(TERMS):
        abort(400)
    setting = get_subject_setting(school_class.year_group, subject, term, year, school_id=require_school())
    _, pupils = class_pupils({'class_id': school_class.id, 'school_id': require_school(), 'academic_year': year})
    allowed = {pupil.id: pupil for pupil in pupils}
    output = []
    for row in data['rows']:
        pupil_id = row.get('pupil_id')
        if pupil_id not in allowed:
            abort(403)
        existing = SubjectResult.query.filter_by(pupil_id=pupil_id, academic_year=year, subject=subject, term=term).first()
        row_setting = setting_for_result(existing, setting) if existing else setting
        try:
            first, second = parse_score(row.get('paper_1_score'), row_setting.paper_1_name), parse_score(row.get('paper_2_score'), row_setting.paper_2_name)
            computed = compute_subject_result_values(row_setting, first, second)
            test_year = int(row.get('assessment_year_group', school_class.year_group))
            if test_year not in range(7):
                raise AssessmentValidationError('Choose a test year from Reception to Year 6.')
            cohort = existing.cohort_year_group if existing and existing.cohort_year_group is not None else cohort_year_group(allowed[pupil_id], year)
            computed['band_label'] = resolve_subject_band_label(percent=computed['combined_percent'], setting=row_setting, pupil_year_group=cohort, assessment_year_group=test_year)
            output.append({'pupil_id': pupil_id, **computed, 'error': None})
        except (ValueError, AssessmentValidationError) as exc:
            output.append({'pupil_id': pupil_id, 'error': str(exc)})
    return {'rows': output}
