"""Routes for Maths Fundamentals."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from io import BytesIO

import qrcode

from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

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


def suggested_intervention_for_level(skill):
    """Return a short practical teaching suggestion based on skill text."""
    skill_text = (skill or '').casefold()
    if 'subitise' in skill_text:
        return 'Use dot patterns, five frames and quick flash images. Ask pupils to say how they saw the quantity.'
    if 'count forwards' in skill_text:
        return 'Practise oral counting sequences, missing number tracks and counting from different starting points.'
    if 'count backwards' in skill_text:
        return 'Use number tracks, countdown games and missing number sequences to rehearse backwards counting.'
    if 'compare' in skill_text:
        return 'Use number lines and quantity cards to compare bigger, smaller and equal values.'
    if 'one more' in skill_text or 'one less' in skill_text:
        return 'Use number tracks, bead strings and quick-fire questions to secure adjacent numbers.'
    if 'decade' in skill_text:
        return 'Practise crossing 29/30, 39/40 and similar boundaries using number lines.'
    if 'hundred' in skill_text:
        return 'Practise crossing 99/100 and 199/200 using counting sticks and number lines.'
    if 'steps' in skill_text:
        return 'Practise counting in equal steps using counting sticks, rhythm and multiplication links.'
    return 'Revisit this skill using concrete resources, oral rehearsal and short daily practice.'


def _default_strand_id(strands):
    for strand in strands:
        name = (strand.name or '').casefold()
        code = (strand.code or '').casefold()
        if name == 'early number sense' or code in {'early_number_sense', 'ens'}:
            return strand.id
    return strands[0].id if strands else None


def _selected_fundamentals_filters(classes, strands):
    selected_class_id = request.args.get('class_id', type=int)
    selected_strand_id = request.args.get('strand_id', type=int) or _default_strand_id(strands)
    class_ids = [school_class.id for school_class in classes]
    if selected_class_id and selected_class_id not in class_ids:
        abort(403)
    if selected_strand_id and selected_strand_id not in [strand.id for strand in strands]:
        abort(404)
    filtered_class_ids = [selected_class_id] if selected_class_id else class_ids
    return selected_class_id, selected_strand_id, filtered_class_ids


def _latest_completed_attempts_for_pupils(class_ids, strand_id):
    if not class_ids or not strand_id:
        return []
    attempts = (FundamentalPupilAttempt.query
        .join(FundamentalSession, FundamentalPupilAttempt.session_id == FundamentalSession.id)
        .join(SchoolClass, FundamentalSession.class_id == SchoolClass.id)
        .join(Pupil, FundamentalPupilAttempt.pupil_id == Pupil.id)
        .filter(
            FundamentalSession.class_id.in_(class_ids),
            FundamentalSession.strand_id == strand_id,
            FundamentalPupilAttempt.is_complete.is_(True),
            FundamentalPupilAttempt.completed_at.isnot(None),
            SchoolClass.is_active.is_(True),
            Pupil.is_active.is_(True),
            Pupil.is_archived.is_(False),
        )
        .order_by(
            FundamentalPupilAttempt.pupil_id,
            FundamentalPupilAttempt.completed_at.desc(),
            FundamentalPupilAttempt.id.desc(),
        )
        .all())
    latest_by_pupil = {}
    for attempt in attempts:
        latest_by_pupil.setdefault(attempt.pupil_id, attempt)
    return list(latest_by_pupil.values())


def _intervention_groups_for_attempts(attempts, strand_id):
    levels = {
        level.level_number: level
        for level in FundamentalLevel.query.filter_by(strand_id=strand_id).all()
    } if strand_id else {}

    grouped = {}
    for attempt in attempts:
        grouped.setdefault(attempt.intervention_level, []).append(attempt)

    groups = []
    for intervention_level, group_attempts in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        level = levels.get(intervention_level)
        groups.append({
            'intervention_level': intervention_level,
            'level': level,
            'attempts': sorted(group_attempts, key=lambda attempt: (attempt.pupil.last_name, attempt.pupil.first_name)),
            'suggested_focus': suggested_intervention_for_level(level.skill if level else ''),
        })
    return groups


def _selected_filter_labels(classes, strands, selected_class_id, selected_strand_id):
    selected_class = next((school_class for school_class in classes if school_class.id == selected_class_id), None)
    selected_strand = next((strand for strand in strands if strand.id == selected_strand_id), None)
    return selected_class, selected_strand


SEQUENCE_QUESTION_TYPES = {
    'sequence',
    'counting',
    'count_forward',
    'count_backward',
    'steps',
    'step_counting',
    'sequence_next',
    'sequence_previous',
    'sequence_next_boundary',
    'sequence_next_100_boundary',
    'equal_steps',
}


def _active_classes_for_user():
    query = SchoolClass.query.filter_by(is_active=True)
    if current_user.is_authenticated:
        if current_user.is_executive_admin:
            school_id = current_school_id()
            if school_id is not None:
                query = query.filter(SchoolClass.school_id == school_id)
        elif current_user.can_manage_school:
            if hasattr(SchoolClass, 'school_id') and hasattr(current_user, 'school_id'):
                query = query.filter_by(school_id=current_user.school_id)
            query = query.filter_by(is_demo=current_user.is_demo)
        else:
            query = query.filter_by(teacher_id=current_user.id, is_demo=current_user.is_demo)
            if hasattr(SchoolClass, 'school_id') and hasattr(current_user, 'school_id'):
                query = query.filter_by(school_id=current_user.school_id)
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
    if current_user.can_manage_school and hasattr(SchoolClass, 'school_id') and hasattr(current_user, 'school_id'):
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


@fundamentals_bp.route('/qr/<int:session_id>')
@login_required
def fundamentals_qr(session_id: int):
    _get_session_or_404(session_id)
    join_url = request.host_url.rstrip('/') + '/fundamentals/join'
    image = qrcode.make(join_url)
    image_io = BytesIO()
    image.save(image_io, 'PNG')
    image_io.seek(0)
    return send_file(image_io, mimetype='image/png')


@fundamentals_bp.route('/scores')
@login_required
def scores():
    classes = _active_classes_for_user()
    class_ids = [school_class.id for school_class in classes]
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()

    selected_class_id = request.args.get('class_id', type=int)
    selected_strand_id = request.args.get('strand_id', type=int)
    selected_status = (request.args.get('status') or 'all').strip().lower()
    pupil_search = (request.args.get('q') or '').strip()

    query = (FundamentalPupilAttempt.query
        .join(FundamentalSession, FundamentalPupilAttempt.session_id == FundamentalSession.id)
        .join(SchoolClass, FundamentalSession.class_id == SchoolClass.id)
        .join(Pupil, FundamentalPupilAttempt.pupil_id == Pupil.id)
        .join(FundamentalStrand, FundamentalSession.strand_id == FundamentalStrand.id)
        .filter(SchoolClass.is_active.is_(True)))

    if not class_ids:
        query = query.filter(False)
    else:
        query = query.filter(FundamentalSession.class_id.in_(class_ids))

    if selected_class_id:
        if selected_class_id not in class_ids:
            abort(403)
        query = query.filter(FundamentalSession.class_id == selected_class_id)

    if selected_strand_id:
        query = query.filter(FundamentalSession.strand_id == selected_strand_id)

    if selected_status == 'complete':
        query = query.filter(FundamentalPupilAttempt.is_complete.is_(True))
    elif selected_status == 'in_progress':
        query = query.filter(FundamentalPupilAttempt.is_complete.is_(False))
    elif selected_status != 'all':
        selected_status = 'all'

    if pupil_search:
        search_term = f'%{pupil_search}%'
        full_name = Pupil.first_name + ' ' + Pupil.last_name
        query = query.filter(or_(Pupil.first_name.ilike(search_term), Pupil.last_name.ilike(search_term), full_name.ilike(search_term)))

    attempts = query.order_by(FundamentalPupilAttempt.created_at.desc(), FundamentalPupilAttempt.id.desc()).all()

    return render_template(
        'fundamentals_scores.html',
        attempts=attempts,
        classes=classes,
        strands=strands,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
        selected_status=selected_status,
        pupil_search=pupil_search,
    )


@fundamentals_bp.route('/levels')
@login_required
def levels():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)

    levels = []
    if selected_strand_id:
        levels = (FundamentalLevel.query
            .filter_by(strand_id=selected_strand_id)
            .order_by(FundamentalLevel.level_number)
            .all())

    latest_attempts = _latest_completed_attempts_for_pupils(class_ids, selected_strand_id)
    rows = []
    for level in levels:
        rows.append({
            'level': level,
            'stuck_count': sum(1 for attempt in latest_attempts if attempt.intervention_level == level.level_number),
            'secure_count': sum(1 for attempt in latest_attempts if attempt.secure_level is not None and attempt.secure_level >= level.level_number),
        })

    return render_template(
        'fundamentals_levels.html',
        classes=classes,
        strands=strands,
        rows=rows,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
    )


@fundamentals_bp.route('/interventions')
@login_required
def interventions():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)
    latest_attempts = _latest_completed_attempts_for_pupils(class_ids, selected_strand_id)
    groups = _intervention_groups_for_attempts(latest_attempts, selected_strand_id)

    return render_template(
        'fundamentals_interventions.html',
        classes=classes,
        strands=strands,
        groups=groups,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
    )


@fundamentals_bp.route('/interventions/print')
@login_required
def interventions_print():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)
    selected_class, selected_strand = _selected_filter_labels(classes, strands, selected_class_id, selected_strand_id)
    latest_attempts = _latest_completed_attempts_for_pupils(class_ids, selected_strand_id)
    groups = _intervention_groups_for_attempts(latest_attempts, selected_strand_id)

    return render_template(
        'fundamentals_interventions_print.html',
        classes=classes,
        groups=groups,
        print_date=datetime.now(timezone.utc),
        selected_class=selected_class,
        selected_class_id=selected_class_id,
        selected_strand=selected_strand,
        selected_strand_id=selected_strand_id,
    )


@fundamentals_bp.route('/levels/<int:level_number>')
@login_required
def level_pupils(level_number: int):
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)
    level = None
    if selected_strand_id:
        level = FundamentalLevel.query.filter_by(strand_id=selected_strand_id, level_number=level_number).first_or_404()
    attempts = [
        attempt for attempt in _latest_completed_attempts_for_pupils(class_ids, selected_strand_id)
        if attempt.intervention_level == level_number
    ]
    attempts.sort(key=lambda attempt: (attempt.pupil.last_name, attempt.pupil.first_name))

    return render_template(
        'fundamentals_level_pupils.html',
        classes=classes,
        strands=strands,
        level=level,
        level_number=level_number,
        attempts=attempts,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
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
    answered_this_level = len(answered_ids)
    return render_template(
        'fundamentals_pupil_question.html',
        attempt=attempt,
        question=question,
        current_level_obj=level,
        answered_this_level=answered_this_level,
    )


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
