"""Standalone Maths Fundamentals routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import MathsFundamentalAttempt, MathsFundamentalQuestion, MathsFundamentalsSession, Pupil, PupilQrToken, School, SchoolClass
from app.services import apply_admin_pupil_filters, build_academic_year_options, build_admin_pupil_filter_state, get_selected_current_academic_year
from app.services.maths_fundamentals import (
    active_session_for_pupil,
    active_strands,
    attempt_status_rows,
    build_teacher_rows,
    class_and_admin_summary,
    close_session,
    filtered_school_pupils,
    get_or_create_qr_token,
    get_or_start_attempt,
    intervention_candidates,
    import_ladder_from_workbook,
    level_colour_class,
    next_question_for_attempt,
    qr_code_data_uri,
    start_session,
    strand_short_name,
    submit_answer,
)
from app.utils import admin_required, current_school_id, demo_filter_classes, get_primary_class_for_user, require_same_school, teacher_required

from . import maths_fundamentals_bp


@maths_fundamentals_bp.app_template_global()
def mf_level_class(level):
    return level_colour_class(level)


@maths_fundamentals_bp.app_template_global()
def mf_strand_short(strand):
    return strand_short_name(strand)




@maths_fundamentals_bp.app_template_global()
def mf_qr_code_data_uri(value):
    return qr_code_data_uri(value)


@maths_fundamentals_bp.route('/teacher', methods=['GET', 'POST'])
@login_required
@teacher_required
def teacher_dashboard():
    school_class = get_primary_class_for_user(current_user)
    if not school_class:
        flash('You need an active class before using Maths Fundamentals.', 'warning')
        return redirect(url_for('dashboards.teacher_dashboard'))
    academic_year = request.values.get('academic_year', get_selected_current_academic_year())
    strands = active_strands()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'start_session':
            strand_id = int(request.form.get('strand_id') or strands[0].id)
            session = start_session(
                school_id=school_class.school_id,
                teacher_id=current_user.id,
                class_id=school_class.id,
                strand_id=strand_id,
                academic_year=academic_year,
                starting_level=int(request.form.get('starting_level') or 1),
                questions_per_level=int(request.form.get('questions_per_level') or 3),
                group_name=request.form.get('group_name'),
            )
            flash('Maths Fundamentals assessment session started. Pupils can now use their QR code.', 'success')
            return redirect(url_for('maths_fundamentals.live_session', session_id=session.id))
        if action == 'close_session':
            session = MathsFundamentalsSession.query.get_or_404(int(request.form.get('session_id')))
            require_same_school(session)
            close_session(session)
            flash('Maths Fundamentals session closed.', 'success')
            return redirect(url_for('maths_fundamentals.teacher_dashboard', academic_year=academic_year))

    filters = build_admin_pupil_filter_state(request.args)
    strand_filter = request.args.get('strand_id', '')
    level_filter = request.args.get('level', '')
    query = Pupil.query.filter_by(class_id=school_class.id, school_id=school_class.school_id)
    pupils = apply_admin_pupil_filters(query, filters).order_by(Pupil.last_name, Pupil.first_name).all()
    rows = build_teacher_rows(pupils, strands, academic_year)
    if level_filter:
        level_value = int(level_filter)
        if strand_filter:
            strand_value = int(strand_filter)
            rows = [row for row in rows if row['levels'].get(strand_value) and row['levels'][strand_value].current_level == level_value]
        else:
            rows = [row for row in rows if any(result and result.current_level == level_value for result in row['levels'].values())]
    open_sessions = MathsFundamentalsSession.query.filter_by(teacher_id=current_user.id, school_id=school_class.school_id, class_id=school_class.id, is_open=True).order_by(MathsFundamentalsSession.opened_at.desc()).all()
    return render_template(
        'maths_fundamentals/teacher_dashboard.html',
        school_class=school_class,
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        strands=strands,
        rows=rows,
        strand_filter=strand_filter,
        level_filter=level_filter,
        open_sessions=open_sessions,
    )


@maths_fundamentals_bp.route('/teacher/pupil/<int:pupil_id>/strand/<int:strand_id>')
@login_required
@teacher_required
def pupil_strand_detail(pupil_id: int, strand_id: int):
    pupil = Pupil.query.get_or_404(pupil_id)
    require_same_school(pupil)
    academic_year = request.args.get('academic_year', get_selected_current_academic_year())
    result = next((r for r in pupil.maths_fundamental_results if r.strand_id == strand_id and r.academic_year == academic_year), None)
    attempts = MathsFundamentalAttempt.query.filter_by(pupil_id=pupil.id, strand_id=strand_id, academic_year=academic_year).order_by(MathsFundamentalAttempt.started_at.desc()).all()
    return render_template('maths_fundamentals/pupil_detail.html', pupil=pupil, result=result, attempts=attempts, strand_id=strand_id, academic_year=academic_year, qr_token=get_or_create_qr_token(pupil))


@maths_fundamentals_bp.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_dashboard():
    if request.method == 'POST' and request.form.get('action') == 'reimport_ladder':
        workbook_path = Path(current_app.root_path) / 'data' / 'Maths_Fundamentals_Ladders_Teaching_and_Questions.xlsx'
        summary = import_ladder_from_workbook(str(workbook_path))
        flash(
            f"Reimported Maths Fundamentals ladder: {summary['strands']} new strands, "
            f"{summary['skills']} new skills, {summary['templates']} new templates. Pupil results were not changed.",
            'success',
        )
        return redirect(url_for('maths_fundamentals.admin_dashboard'))

    school_id = current_school_id()
    academic_year = request.args.get('academic_year', get_selected_current_academic_year())
    filters = build_admin_pupil_filter_state(request.args)
    class_id = request.args.get('class_id') or ''
    year_group = request.args.get('year_group') or ''
    strand_filter = request.args.get('strand_id') or ''
    strands = active_strands()
    pupils = filtered_school_pupils(school_id, filters, class_id=class_id, year_group=year_group)
    summary = class_and_admin_summary(pupils, strands, academic_year)
    candidates = intervention_candidates(pupils, strands, academic_year)
    rows = build_teacher_rows(pupils, strands, academic_year)
    class_options = demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).order_by(SchoolClass.year_group, SchoolClass.name).all()
    schools = School.query.order_by(School.name).all() if current_user.is_executive_admin else []
    return render_template(
        'maths_fundamentals/admin_dashboard.html',
        academic_year=academic_year,
        academic_year_options=build_academic_year_options(academic_year),
        filters=filters,
        class_id=class_id,
        year_group=year_group,
        strand_filter=strand_filter,
        strands=strands,
        rows=rows,
        summary=summary,
        candidates=candidates,
        class_options=class_options,
        schools=schools,
    )


@maths_fundamentals_bp.route('/admin/interventions')
@login_required
@admin_required
def admin_interventions():
    school_id = current_school_id()
    academic_year = request.args.get('academic_year', get_selected_current_academic_year())
    filters = build_admin_pupil_filter_state(request.args)
    pupils = filtered_school_pupils(school_id, filters, class_id=request.args.get('class_id'), year_group=request.args.get('year_group'))
    strands = active_strands()
    candidates = intervention_candidates(pupils, strands, academic_year)
    return render_template('maths_fundamentals/interventions.html', academic_year=academic_year, filters=filters, candidates=candidates)


@maths_fundamentals_bp.route('/session/<int:session_id>/live', methods=['GET', 'POST'])
@login_required
@teacher_required
def live_session(session_id: int):
    session = MathsFundamentalsSession.query.get_or_404(session_id)
    require_same_school(session)
    if session.teacher_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'close':
            close_session(session)
            flash('Session closed.', 'success')
        elif action == 'restart':
            for attempt in session.attempts:
                db.session.delete(attempt)
            db.session.commit()
            flash('Session attempts restarted.', 'success')
        elif action == 'pause':
            session.is_open = False
            session.closed_at = datetime.now(timezone.utc)
            db.session.add(session)
            db.session.commit()
            flash('Session paused. Start a new session when pupils should resume.', 'warning')
        return redirect(url_for('maths_fundamentals.live_session', session_id=session.id))
    return render_template('maths_fundamentals/live_session.html', session=session, rows=attempt_status_rows(session))


@maths_fundamentals_bp.route('/qr/<token>', methods=['GET', 'POST'])
def pupil_qr(token: str):
    qr_token = PupilQrToken.query.filter_by(token=token, is_active=True).first_or_404()
    pupil = qr_token.pupil
    qr_token.last_used_at = datetime.now(timezone.utc)
    db.session.add(qr_token)
    session = active_session_for_pupil(pupil)
    if not session:
        db.session.commit()
        return render_template('maths_fundamentals/qr_waiting.html', pupil=pupil)
    attempt = get_or_start_attempt(session, pupil)
    if request.method == 'POST':
        question_id = int(request.form.get('question_id'))
        question = MathsFundamentalQuestion.query.get_or_404(question_id)
        if question.attempt_id != attempt.id:
            abort(403)
        attempt = submit_answer(question, request.form.get('answer', ''))
        if attempt.status == 'completed':
            return redirect(url_for('maths_fundamentals.pupil_qr', token=token))
    question = next_question_for_attempt(attempt)
    return render_template('maths_fundamentals/pupil_assessment.html', pupil=pupil, session=session, attempt=attempt, question=question)
