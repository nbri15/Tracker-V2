"""Routes for Maths Fundamentals."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    FundamentalLevel,
    FundamentalPupilAttempt,
    FundamentalQuestion,
    FundamentalResponse,
    FundamentalSession,
    FundamentalStrand,
    Pupil,
    SchoolClass,
)
from app.utils import current_school_id
from . import fundamentals_bp

SEQUENCE_QUESTION_TYPES = {'sequence', 'counting', 'count_forward', 'count_backward', 'steps', 'step_counting'}


def _active_classes_for_user():
    query = SchoolClass.query.filter_by(is_active=True)
    if current_user.is_authenticated and not current_user.is_executive_admin:
        if hasattr(SchoolClass, 'school_id') and hasattr(current_user, 'school_id'):
            query = query.filter_by(school_id=current_user.school_id)
        query = query.filter_by(is_demo=current_user.is_demo)
    return query.order_by(SchoolClass.year_group, SchoolClass.name).all()


def _classes_with_active_sessions():
    query = (SchoolClass.query
        .join(FundamentalSession, FundamentalSession.class_id == SchoolClass.id)
        .filter(SchoolClass.is_active.is_(True), FundamentalSession.is_active.is_(True)))
    if hasattr(SchoolClass, 'school_id'):
        school_id = request.values.get('school_id', type=int)
        if school_id is None:
            return []
        query = query.filter(SchoolClass.school_id == school_id)
    return query.distinct().order_by(SchoolClass.year_group, SchoolClass.name).all()


def _active_session_for_class(class_id: int):
    return (FundamentalSession.query
        .join(SchoolClass, FundamentalSession.class_id == SchoolClass.id)
        .filter(FundamentalSession.class_id == class_id, FundamentalSession.is_active.is_(True), SchoolClass.is_active.is_(True))
        .order_by(FundamentalSession.created_at.desc()).first())


def format_fundamental_question_text(question: FundamentalQuestion) -> str:
    text = (question.question_text or '').strip()
    question_type = (question.question_type or '').strip().lower()
    if question_type not in SEQUENCE_QUESTION_TYPES or ',' in text:
        return text
    return ', '.join(text.split())


def _can_access_class(school_class: SchoolClass) -> bool:
    if current_user.is_executive_admin:
        return True
    if hasattr(SchoolClass, 'school_id') and hasattr(current_user, 'school_id'):
        return school_class.school_id == current_school_id() and school_class.is_demo == current_user.is_demo
    return school_class.teacher_id == current_user.id and school_class.is_demo == current_user.is_demo


def _get_session_or_404(session_id: int) -> FundamentalSession:
    session = FundamentalSession.query.get_or_404(session_id)
    if not _can_access_class(session.school_class):
        abort(403)
    return session


def _default_start_level(school_class: SchoolClass) -> int:
    return 5 if school_class.year_group and school_class.year_group >= 3 else 1


@fundamentals_bp.route('')
@login_required
def home():
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    classes = _active_classes_for_user()
    class_ids = [c.id for c in classes]
    active_sessions = []
    if class_ids:
        active_sessions = (FundamentalSession.query
            .filter(FundamentalSession.class_id.in_(class_ids), FundamentalSession.is_active.is_(True))
            .order_by(FundamentalSession.created_at.desc()).all())
    return render_template('fundamentals_home.html', strands=strands, classes=classes, active_sessions=active_sessions)


@fundamentals_bp.route('/start', methods=['GET', 'POST'])
@login_required
def start():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id = request.values.get('class_id', type=int) or (classes[0].id if classes else None)
    selected_class = next((c for c in classes if c.id == selected_class_id), None)

    if request.method == 'POST':
        school_class = SchoolClass.query.get_or_404(request.form.get('class_id', type=int))
        if not _can_access_class(school_class):
            abort(403)
        strand = FundamentalStrand.query.get_or_404(request.form.get('strand_id', type=int))
        start_level = request.form.get('start_level', type=int) or _default_start_level(school_class)
        FundamentalSession.query.filter_by(class_id=school_class.id, strand_id=strand.id, is_active=True).update({'is_active': False})
        session = FundamentalSession(class_id=school_class.id, teacher_id=current_user.id, strand_id=strand.id, start_level=start_level, is_active=True)
        db.session.add(session)
        db.session.commit()
        flash('Maths Fundamentals session started.', 'success')
        return redirect(url_for('fundamentals.session_detail', session_id=session.id))

    return render_template('fundamentals_start.html', classes=classes, strands=strands, selected_class=selected_class, default_level=_default_start_level(selected_class) if selected_class else 1)


@fundamentals_bp.route('/session/<int:session_id>')
@login_required
def session_detail(session_id: int):
    session = _get_session_or_404(session_id)
    pupils = session.school_class.pupils.filter_by(is_active=True, is_archived=False).order_by(Pupil.last_name, Pupil.first_name).all()
    attempts = FundamentalPupilAttempt.query.filter_by(session_id=session.id).all()
    attempts_by_pupil = {attempt.pupil_id: attempt for attempt in attempts}
    answered_counts = {
        attempt.id: FundamentalResponse.query.filter_by(attempt_id=attempt.id).count()
        for attempt in attempts
    }
    return render_template(
        'fundamentals_session.html',
        session=session,
        pupils=pupils,
        attempts=attempts_by_pupil,
        answered_counts=answered_counts,
    )


@fundamentals_bp.route('/session/<int:session_id>/stop', methods=['POST'])
@login_required
def stop_session(session_id: int):
    session = _get_session_or_404(session_id)
    session.is_active = False
    db.session.commit()
    flash('Maths Fundamentals session stopped.', 'success')
    return redirect(url_for('fundamentals.session_detail', session_id=session.id))


@fundamentals_bp.route('/pupil', methods=['GET', 'POST'])
def pupil_login():
    classes = _classes_with_active_sessions()
    pupils = []
    selected_class_id = request.values.get('class_id', type=int)
    selected_class = next((school_class for school_class in classes if school_class.id == selected_class_id), None)
    if selected_class:
        pupils = Pupil.query.filter_by(class_id=selected_class_id, is_active=True, is_archived=False).order_by(Pupil.last_name, Pupil.first_name).all()
    if request.method == 'POST':
        pupil = Pupil.query.get_or_404(request.form.get('pupil_id', type=int))
        if not selected_class or pupil.class_id != selected_class.id:
            flash('Please check your class and name.', 'danger')
            return render_template('fundamentals_pupil_login.html', classes=classes, pupils=pupils, selected_class_id=selected_class_id)
        session = _active_session_for_class(selected_class.id)
        if not session:
            return render_template('fundamentals_pupil_login.html', classes=classes, pupils=pupils, selected_class_id=selected_class_id, no_session=True)
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=session.id, pupil_id=pupil.id).first()
        if not attempt:
            attempt = FundamentalPupilAttempt(session_id=session.id, pupil_id=pupil.id, current_level=session.start_level)
            db.session.add(attempt)
            db.session.commit()
        if attempt.is_complete:
            return redirect(url_for('fundamentals.pupil_complete', attempt_id=attempt.id))
        return redirect(url_for('fundamentals.pupil_question', attempt_id=attempt.id))
    return render_template('fundamentals_pupil_login.html', classes=classes, pupils=pupils, selected_class_id=selected_class_id)


@fundamentals_bp.route('/join', methods=['GET', 'POST'])
def join():
    return pupil_login()


def _complete_attempt(attempt: FundamentalPupilAttempt):
    attempt.is_complete = True
    attempt.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for('fundamentals.pupil_complete', attempt_id=attempt.id))


@fundamentals_bp.route('/pupil/question/<int:attempt_id>', methods=['GET', 'POST'])
def pupil_question(attempt_id: int):
    attempt = FundamentalPupilAttempt.query.get_or_404(attempt_id)
    if attempt.pupil.class_id != attempt.session.class_id or not attempt.session.is_active:
        abort(404)
    if attempt.is_complete:
        return redirect(url_for('fundamentals.pupil_complete', attempt_id=attempt.id))
    level = FundamentalLevel.query.filter_by(strand_id=attempt.session.strand_id, level_number=attempt.current_level).first()
    if not level:
        return _complete_attempt(attempt)
    if request.method == 'POST':
        question = FundamentalQuestion.query.get_or_404(request.form.get('question_db_id', type=int))
        if question.strand_id != attempt.session.strand_id or question.level_number != attempt.current_level:
            abort(404)
        pupil_answer = (request.form.get('answer') or '').strip()
        is_correct = pupil_answer.casefold() == (question.answer or '').strip().casefold()
        db.session.add(FundamentalResponse(attempt_id=attempt.id, question_id=question.id, level_number=attempt.current_level, pupil_answer=pupil_answer, is_correct=is_correct))
        db.session.commit()
        answered = FundamentalResponse.query.filter_by(attempt_id=attempt.id, level_number=attempt.current_level).all()
        if len(answered) >= 10:
            score = round((sum(1 for r in answered if r.is_correct) / len(answered)) * 100)
            if score >= level.pass_mark:
                attempt.secure_level = attempt.current_level
                attempt.below_70_streak = 0
            else:
                if attempt.intervention_level is None:
                    attempt.intervention_level = attempt.current_level
                attempt.below_70_streak += 1
            attempt.current_level += 1
            next_level = FundamentalLevel.query.filter_by(strand_id=attempt.session.strand_id, level_number=attempt.current_level).first()
            if attempt.below_70_streak >= 2 or not next_level:
                return _complete_attempt(attempt)
            db.session.commit()
        return redirect(url_for('fundamentals.pupil_question', attempt_id=attempt.id))

    answered_ids = [r.question_id for r in FundamentalResponse.query.filter_by(attempt_id=attempt.id, level_number=attempt.current_level).all()]
    questions = FundamentalQuestion.query.filter_by(strand_id=attempt.session.strand_id, level_number=attempt.current_level).all()
    remaining = [q for q in questions if q.id not in answered_ids]
    if not remaining:
        return redirect(url_for('fundamentals.pupil_question', attempt_id=attempt.id))
    question = random.choice(remaining)
    progress = len(answered_ids) + 1
    formatted_question = format_fundamental_question_text(question)
    return render_template('fundamentals_pupil_question.html', attempt=attempt, question=question, progress=progress, question_text=formatted_question)


@fundamentals_bp.route('/attempt/<int:attempt_id>')
@login_required
def attempt_detail(attempt_id: int):
    attempt = FundamentalPupilAttempt.query.get_or_404(attempt_id)
    school_class = attempt.session.school_class
    if current_user.is_executive_admin:
        pass
    elif current_user.can_manage_school:
        if not _can_access_class(school_class):
            abort(403)
    elif school_class.teacher_id != current_user.id or school_class.is_demo != current_user.is_demo:
        abort(403)

    responses = (FundamentalResponse.query
        .filter_by(attempt_id=attempt.id)
        .order_by(FundamentalResponse.level_number, FundamentalResponse.created_at, FundamentalResponse.id)
        .all())
    response_rows = [
        {
            'response': response,
            'question_text': format_fundamental_question_text(response.question),
        }
        for response in responses
    ]
    return render_template('fundamentals_attempt_detail.html', attempt=attempt, response_rows=response_rows)


@fundamentals_bp.route('/pupil/complete/<int:attempt_id>')
def pupil_complete(attempt_id: int):
    attempt = FundamentalPupilAttempt.query.get_or_404(attempt_id)
    if attempt.pupil.class_id != attempt.session.class_id:
        abort(404)
    return render_template('fundamentals_pupil_complete.html', attempt=attempt)
