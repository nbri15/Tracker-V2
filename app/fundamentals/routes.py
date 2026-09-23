"""Routes for Maths Fundamentals."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from io import BytesIO

import qrcode

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

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
from app.services import get_school_working_academic_year
from app.utils import current_school_id
from . import fundamentals_bp
from .presentation import answers_match, question_presentation


SESSION_TOKEN_SALT = 'maths-fundamentals-session-v1'
ATTEMPT_TOKEN_SALT = 'maths-fundamentals-attempt-v1'
QUESTION_TOKEN_SALT = 'maths-fundamentals-question-v1'
DEFAULT_TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60


def _token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        signer_kwargs={'digest_method': hashlib.sha256},
    )


def _token_max_age() -> int:
    return int(current_app.config.get('FUNDAMENTALS_TOKEN_MAX_AGE', DEFAULT_TOKEN_MAX_AGE_SECONDS))


def _load_signed_token(token: str, *, salt: str, kind: str) -> dict:
    try:
        payload = _token_serializer().loads(token, salt=salt, max_age=_token_max_age())
    except (BadSignature, SignatureExpired):
        abort(404)
    if not isinstance(payload, dict) or payload.get('kind') != kind:
        abort(404)
    return payload


def make_session_token(session: FundamentalSession) -> str:
    """Return a signed public token bound to one exact assessment session."""
    return _token_serializer().dumps(
        {
            'kind': 'session',
            'session_id': session.id,
            'class_id': session.class_id,
            'school_id': session.school_class.school_id,
            'strand_id': session.strand_id,
        },
        salt=SESSION_TOKEN_SALT,
    )


def make_attempt_token(attempt: FundamentalPupilAttempt) -> str:
    """Return a signed public token bound to one pupil attempt and session."""
    return _token_serializer().dumps(
        {
            'kind': 'attempt',
            'attempt_id': attempt.id,
            'session_id': attempt.session_id,
            'pupil_id': attempt.pupil_id,
            'class_id': attempt.session.class_id,
            'school_id': attempt.session.school_class.school_id,
            'strand_id': attempt.session.strand_id,
        },
        salt=ATTEMPT_TOKEN_SALT,
    )


def _make_question_token(attempt: FundamentalPupilAttempt, question: FundamentalQuestion) -> str:
    return _token_serializer().dumps(
        {
            'kind': 'question',
            'attempt_id': attempt.id,
            'session_id': attempt.session_id,
            'question_id': question.id,
            'level_number': attempt.current_level,
        },
        salt=QUESTION_TOKEN_SALT,
    )


def _valid_public_session(session: FundamentalSession, *, require_active: bool = True) -> bool:
    school_class = session.school_class
    school = school_class.school if school_class else None
    if not school_class or not school:
        return False
    if require_active and not session.is_active:
        return False
    return bool(school_class.is_active and school.is_active and not school.is_archived)


def _session_from_token(session_token: str, *, require_active: bool = True) -> FundamentalSession:
    payload = _load_signed_token(session_token, salt=SESSION_TOKEN_SALT, kind='session')
    session = db.session.get(FundamentalSession, payload.get('session_id'))
    if not session:
        abort(404)
    if payload.get('class_id') != session.class_id or payload.get('strand_id') != session.strand_id:
        abort(404)
    if payload.get('school_id') != session.school_class.school_id:
        abort(404)
    if not _valid_public_session(session, require_active=require_active):
        abort(404)
    return session


def _validate_attempt_scope(attempt: FundamentalPupilAttempt, *, require_active: bool = True) -> None:
    session = attempt.session
    pupil = attempt.pupil
    if not session or not pupil or not _valid_public_session(session, require_active=require_active):
        abort(404)
    if pupil.class_id != session.class_id:
        abort(404)
    if pupil.school_id != session.school_class.school_id:
        abort(404)
    if not pupil.is_active or pupil.is_archived or pupil.is_demo != session.school_class.is_demo:
        abort(404)


def _attempt_from_token(attempt_token: str, *, require_active: bool = True) -> FundamentalPupilAttempt:
    payload = _load_signed_token(attempt_token, salt=ATTEMPT_TOKEN_SALT, kind='attempt')
    attempt = db.session.get(FundamentalPupilAttempt, payload.get('attempt_id'))
    if not attempt or payload.get('session_id') != attempt.session_id:
        abort(404)
    if (
        payload.get('pupil_id') != attempt.pupil_id
        or payload.get('class_id') != attempt.session.class_id
        or payload.get('school_id') != attempt.session.school_class.school_id
        or payload.get('strand_id') != attempt.session.strand_id
    ):
        abort(404)
    _validate_attempt_scope(attempt, require_active=require_active)
    return attempt


def _question_from_token(question_token: str, attempt: FundamentalPupilAttempt) -> tuple[FundamentalQuestion, int]:
    payload = _load_signed_token(question_token, salt=QUESTION_TOKEN_SALT, kind='question')
    if payload.get('attempt_id') != attempt.id or payload.get('session_id') != attempt.session_id:
        abort(404)
    question = db.session.get(FundamentalQuestion, payload.get('question_id'))
    token_level = payload.get('level_number')
    if not question or question.strand_id != attempt.session.strand_id:
        abort(404)
    if question.level_number != token_level:
        abort(404)
    return question, token_level


def _attempt_public_redirect(attempt: FundamentalPupilAttempt):
    attempt_token = make_attempt_token(attempt)
    endpoint = 'fundamentals.pupil_complete' if attempt.is_complete else 'fundamentals.pupil_question'
    return redirect(url_for(endpoint, attempt_token=attempt_token))


NUMBER_BONDS_INTERVENTIONS = (
    ('bonds within 5', 'Use counters, five frames and part-whole models to compose and partition quantities within 5.'),
    ('bonds to 5', 'Practise pairs that total 5 using fingers, five frames and missing-number games.'),
    ('bonds within 10', 'Use ten frames and counters to explore different ways to compose numbers within 10.'),
    ('bonds to 10', 'Rehearse pairs to 10 using ten frames, bead strings and quick-fire recall.'),
    ('bonds to 20', 'Use known bonds to 10 to derive pairs to 20.'),
    ('crossing 10', 'Use ten frames and make-ten strategies to bridge through 10.'),
    ('bonds to 50', 'Use place-value counters and known facts to derive complements to 50.'),
    ('bonds to 100 in tens', 'Rehearse multiples-of-ten complements to 100.'),
    ('bonds to 1000', 'Use place-value grids and complements to 100 to derive complements to 1000.'),
    ('bonds to 100', 'Partition into tens and ones, then find the complement to 100.'),
    ('decimal bonds to 1', 'Use hundred squares, decimal number lines and money contexts.'),
    ('decimal bonds to 10', 'Partition whole numbers and decimals to find complements to 10.'),
)

PLACE_VALUE_INTERVENTIONS = (
    ('unitising', 'Use base-ten blocks to exchange 10 ones for 1 ten and 10 tens for 1 hundred.'),
    ('cross tens', 'Count forwards and backwards across tens boundaries using base-ten blocks and number lines.'),
    ('cross hundreds', 'Model exchanges across hundreds with place-value counters and number lines.'),
    ('cross thousands', 'Use place-value charts and equal jumps to cross 1,000 and 10,000 boundaries.'),
    ('flexible partitioning', 'Build the same number in several ways, including regrouped and zero-placeholder partitions.'),
    ('number lines', 'Mark endpoints, intervals and midpoints before estimating each number position.'),
    ('more or less', 'Use a place-value chart to identify which digits change and which stay the same.'),
    ('powers of ten', 'Use place-value charts to track digit value when multiplying or dividing by 10.'),
    ('rounding', 'Locate numbers between adjacent multiples and reason from the midpoint.'),
    ('negative', 'Count and compare on a number line that crosses zero.'),
    ('tenths and hundredths', 'Connect decimal grids, place-value charts and decimal number lines.'),
    ('decimal composition', 'Compose and partition decimals using tenths, hundredths and thousandths.'),
)


def suggested_intervention_for_level(skill):
    """Return a short practical teaching suggestion based on skill text."""
    skill_text = (skill or '').casefold()
    for skill_fragment, suggestion in NUMBER_BONDS_INTERVENTIONS:
        if skill_fragment in skill_text:
            return suggestion
    for skill_fragment, suggestion in PLACE_VALUE_INTERVENTIONS:
        if skill_fragment in skill_text:
            return suggestion
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


def _latest_completed_attempts_for_pupils(class_ids, strand_id, academic_year=None):
    if not class_ids or not strand_id:
        return []
    query = (FundamentalPupilAttempt.query
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
        ))
    if academic_year:
        query = query.filter(or_(
            FundamentalSession.academic_year == academic_year,
            FundamentalSession.academic_year.is_(None),
        ))
    attempts = (query
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


def _fundamentals_academic_year(classes) -> str | None:
    """Return the selected school's stored year for current Fundamentals views."""
    if not classes:
        return None
    return get_school_working_academic_year(classes[0].school_id).name


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


def _default_start_level(school_class: SchoolClass, strand: FundamentalStrand | None = None) -> int:
    if strand and (strand.code or '').casefold() == 'pv':
        return {
            0: 1,
            1: 2,
            2: 5,
            3: 6,
            4: 10,
            5: 12,
            6: 15,
        }.get(school_class.year_group, 1)
    if strand and (strand.code or '').casefold() == 'nb':
        return 5 if school_class.year_group and school_class.year_group >= 3 else 1
    return 5 if school_class.year_group and school_class.year_group >= 3 else 1


@fundamentals_bp.route('')
@login_required
def home():
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    classes = _active_classes_for_user()
    class_ids = [c.id for c in classes]
    academic_year = _fundamentals_academic_year(classes)
    active_sessions = []
    if class_ids:
        active_sessions = (FundamentalSession.query
            .filter(
                FundamentalSession.class_id.in_(class_ids),
                or_(
                    FundamentalSession.academic_year == academic_year,
                    FundamentalSession.academic_year.is_(None),
                ),
                FundamentalSession.is_active.is_(True),
            )
            .order_by(FundamentalSession.created_at.desc()).all())
    return render_template('fundamentals_home.html', strands=strands, classes=classes, active_sessions=active_sessions)


@fundamentals_bp.route('/start', methods=['GET', 'POST'])
@login_required
def start():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id = request.values.get('class_id', type=int) or (classes[0].id if classes else None)
    selected_class = next((c for c in classes if c.id == selected_class_id), None)
    selected_strand_id = request.values.get('strand_id', type=int) or _default_strand_id(strands)
    selected_strand = next((strand for strand in strands if strand.id == selected_strand_id), None)
    levels_by_strand = {
        strand.id: [level.level_number for level in FundamentalLevel.query.filter_by(strand_id=strand.id).order_by(FundamentalLevel.level_number).all()]
        for strand in strands
    }
    defaults_by_strand = {
        strand.id: (_default_start_level(selected_class, strand) if selected_class else 1)
        for strand in strands
    }

    if request.method == 'POST':
        school_class = SchoolClass.query.get_or_404(request.form.get('class_id', type=int))
        if not _can_access_class(school_class):
            abort(403)
        strand = FundamentalStrand.query.get_or_404(request.form.get('strand_id', type=int))
        start_level = request.form.get('start_level', type=int) or _default_start_level(school_class, strand)
        if not FundamentalLevel.query.filter_by(strand_id=strand.id, level_number=start_level).first():
            flash('Please choose a valid start level for the selected strand.', 'danger')
            return redirect(url_for('fundamentals.start', class_id=school_class.id, strand_id=strand.id))
        FundamentalSession.query.filter_by(class_id=school_class.id, strand_id=strand.id, is_active=True).update({'is_active': False})
        academic_year = get_school_working_academic_year(school_class.school_id).name
        session = FundamentalSession(
            class_id=school_class.id,
            teacher_id=current_user.id,
            strand_id=strand.id,
            academic_year=academic_year,
            start_level=start_level,
            is_active=True,
        )
        db.session.add(session)
        db.session.commit()
        current_app.logger.info(
            "Created fundamentals session id=%s class_id=%s strand_id=%s active=%s",
            session.id,
            session.class_id,
            session.strand_id,
            session.is_active,
        )
        flash('Maths Fundamentals session started.', 'success')
        return redirect(url_for('fundamentals.session_detail', session_id=session.id))

    return render_template(
        'fundamentals_start.html',
        classes=classes,
        strands=strands,
        selected_class=selected_class,
        selected_strand_id=selected_strand_id,
        levels_by_strand=levels_by_strand,
        defaults_by_strand=defaults_by_strand,
        default_level=_default_start_level(selected_class, selected_strand) if selected_class else 1,
    )


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
    pupil_join_path = url_for('fundamentals.pupil_join', session_token=make_session_token(session))
    pupil_join_url = request.host_url.rstrip('/') + pupil_join_path
    return render_template(
        'fundamentals_session.html',
        session=session,
        pupils=pupils,
        attempts=attempts_by_pupil,
        answered_counts=answered_counts,
        pupil_join_path=pupil_join_path,
        pupil_join_url=pupil_join_url,
    )


@fundamentals_bp.route('/qr/<int:session_id>')
@login_required
def fundamentals_qr(session_id: int):
    session = _get_session_or_404(session_id)
    join_path = url_for('fundamentals.pupil_join', session_token=make_session_token(session))
    join_url = request.host_url.rstrip('/') + join_path
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

    latest_attempts = _latest_completed_attempts_for_pupils(
        class_ids, selected_strand_id, _fundamentals_academic_year(classes)
    )
    example_questions = {}
    if selected_strand_id:
        for question in (FundamentalQuestion.query
                .filter_by(strand_id=selected_strand_id)
                .order_by(FundamentalQuestion.level_number, FundamentalQuestion.question_id)
                .all()):
            example_questions.setdefault(question.level_number, question)
    rows = []
    for level in levels:
        rows.append({
            'level': level,
            'example_question': example_questions.get(level.level_number),
            'stuck_count': sum(1 for attempt in latest_attempts if attempt.intervention_level == level.level_number),
            'secure_count': sum(1 for attempt in latest_attempts if attempt.secure_level is not None and attempt.secure_level >= level.level_number),
        })

    selected_class, selected_strand = _selected_filter_labels(
        classes, strands, selected_class_id, selected_strand_id
    )
    return render_template(
        'fundamentals_levels.html',
        classes=classes,
        strands=strands,
        rows=rows,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
        selected_strand=selected_strand,
    )


@fundamentals_bp.route('/interventions')
@login_required
def interventions():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)
    latest_attempts = _latest_completed_attempts_for_pupils(
        class_ids, selected_strand_id, _fundamentals_academic_year(classes)
    )
    groups = _intervention_groups_for_attempts(latest_attempts, selected_strand_id)

    selected_class, selected_strand = _selected_filter_labels(
        classes, strands, selected_class_id, selected_strand_id
    )
    return render_template(
        'fundamentals_interventions.html',
        classes=classes,
        strands=strands,
        groups=groups,
        selected_class_id=selected_class_id,
        selected_strand_id=selected_strand_id,
        selected_strand=selected_strand,
    )


@fundamentals_bp.route('/interventions/print')
@login_required
def interventions_print():
    classes = _active_classes_for_user()
    strands = FundamentalStrand.query.order_by(FundamentalStrand.name).all()
    selected_class_id, selected_strand_id, class_ids = _selected_fundamentals_filters(classes, strands)
    selected_class, selected_strand = _selected_filter_labels(classes, strands, selected_class_id, selected_strand_id)
    latest_attempts = _latest_completed_attempts_for_pupils(
        class_ids, selected_strand_id, _fundamentals_academic_year(classes)
    )
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
        attempt for attempt in _latest_completed_attempts_for_pupils(
            class_ids, selected_strand_id, _fundamentals_academic_year(classes)
        )
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



def _active_pupils_for_session(session: FundamentalSession):
    return (Pupil.query
        .filter(
            Pupil.class_id == session.class_id,
            Pupil.school_id == session.school_class.school_id,
            Pupil.is_active.is_(True),
            Pupil.is_archived.is_(False),
            Pupil.is_demo == session.school_class.is_demo,
        )
        .order_by(Pupil.last_name.asc(), Pupil.first_name.asc())
        .all())


@fundamentals_bp.route('/join/<session_token>', methods=['GET', 'POST'])
def pupil_join(session_token: str):
    session = _session_from_token(session_token)
    pupils = _active_pupils_for_session(session)
    if request.method == 'POST':
        pupil = (Pupil.query
            .filter(
                Pupil.id == request.form.get('pupil_id', type=int),
                Pupil.class_id == session.class_id,
                Pupil.school_id == session.school_class.school_id,
                Pupil.is_active.is_(True),
                Pupil.is_archived.is_(False),
                Pupil.is_demo == session.school_class.is_demo,
            )
            .first_or_404())
        attempt = FundamentalPupilAttempt.query.filter_by(session_id=session.id, pupil_id=pupil.id).first()
        if not attempt:
            attempt = FundamentalPupilAttempt(session_id=session.id, pupil_id=pupil.id, current_level=session.start_level)
            db.session.add(attempt)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                attempt = FundamentalPupilAttempt.query.filter_by(session_id=session.id, pupil_id=pupil.id).first_or_404()
        _validate_attempt_scope(attempt)
        return _attempt_public_redirect(attempt)
    return render_template('fundamentals_pupil_login.html', session=session, pupils=pupils)


def _complete_attempt(attempt: FundamentalPupilAttempt):
    attempt.is_complete = True
    attempt.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return _attempt_public_redirect(attempt)


@fundamentals_bp.route('/pupil/question/<attempt_token>', methods=['GET', 'POST'])
def pupil_question(attempt_token: str):
    attempt = _attempt_from_token(attempt_token)
    if attempt.is_complete:
        return _attempt_public_redirect(attempt)
    level = FundamentalLevel.query.filter_by(strand_id=attempt.session.strand_id, level_number=attempt.current_level).first()
    if not level:
        return _complete_attempt(attempt)
    if request.method == 'POST':
        question, token_level = _question_from_token(request.form.get('question_token') or '', attempt)
        attempt = (FundamentalPupilAttempt.query
            .filter_by(id=attempt.id)
            .populate_existing()
            .with_for_update()
            .first_or_404())
        _validate_attempt_scope(attempt)
        existing_response = FundamentalResponse.query.filter_by(attempt_id=attempt.id, question_id=question.id).first()
        if existing_response:
            return _attempt_public_redirect(attempt)
        if question.level_number != attempt.current_level or token_level != attempt.current_level:
            abort(404)
        pupil_answer = (request.form.get('answer') or '').strip()
        is_correct = answers_match(pupil_answer, question.answer)
        db.session.add(FundamentalResponse(
            attempt_id=attempt.id,
            question_id=question.id,
            level_number=attempt.current_level,
            pupil_answer=pupil_answer,
            is_correct=is_correct,
            question_text_snapshot=question.question_text,
            correct_answer_snapshot=question.answer,
            skill_snapshot=level.skill,
        ))
        try:
            db.session.flush()
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
                    attempt.is_complete = True
                    attempt.completed_at = datetime.now(timezone.utc)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            attempt = _attempt_from_token(attempt_token)
        return _attempt_public_redirect(attempt)

    answered_ids = [r.question_id for r in FundamentalResponse.query.filter_by(attempt_id=attempt.id, level_number=attempt.current_level).all()]
    questions = FundamentalQuestion.query.filter_by(strand_id=attempt.session.strand_id, level_number=attempt.current_level).all()
    remaining = [q for q in questions if q.id not in answered_ids]
    if not remaining:
        return _attempt_public_redirect(attempt)
    question = random.choice(remaining)
    answered_this_level = len(answered_ids)
    return render_template(
        'fundamentals_pupil_question.html',
        attempt=attempt,
        question=question,
        question_token=_make_question_token(attempt, question),
        current_level_obj=level,
        answered_this_level=answered_this_level,
        presentation=question_presentation(question),
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
            'question_text': response.question_text_snapshot or format_fundamental_question_text(response.question),
            'correct_answer': response.correct_answer_snapshot or response.question.answer,
        }
        for response in responses
    ]
    return render_template('fundamentals_attempt_detail.html', attempt=attempt, response_rows=response_rows)


@fundamentals_bp.route('/pupil/complete/<attempt_token>')
def pupil_complete(attempt_token: str):
    attempt = _attempt_from_token(attempt_token, require_active=False)
    if not attempt.is_complete:
        return _attempt_public_redirect(attempt)
    return render_template('fundamentals_pupil_complete.html', attempt=attempt)
