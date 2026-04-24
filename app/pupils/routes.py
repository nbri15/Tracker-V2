"""Pupil directory and history routes."""

from __future__ import annotations

from collections import defaultdict

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.extensions import db
from app.models import (
    GapQuestion,
    GapScore,
    GapTemplate,
    Intervention,
    PhonicsScore,
    Pupil,
    PupilClassHistory,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SatsResult,
    SatsWritingResult,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    WritingResult,
)
from app.utils import teacher_or_admin_required

from . import pupils_bp

BAND_RANK = {'Working Towards': 1, 'WT': 1, 'On Track': 2, 'OT': 2, 'Exceeding': 3, 'EXS': 3, 'GDS': 3, 'Exceeding+': 3}
BAND_THEME = {'Working Towards': 'danger', 'WT': 'danger', 'On Track': 'success', 'OT': 'success', 'Exceeding': 'warning', 'EXS': 'warning', 'GDS': 'warning'}


@pupils_bp.route('')
@login_required
@teacher_or_admin_required
def directory():
    filters = _build_pupil_filters(request.args)
    query = Pupil.query.join(Pupil.school_class)

    if current_user.is_teacher:
        teacher_class_ids = [school_class.id for school_class in current_user.classes.filter_by(is_active=True).all()]
        if not teacher_class_ids:
            pupils = []
            return render_template('pupils/list.html', pupils=pupils, filters=filters, class_options=[], year_group_options=[])
        query = query.filter(Pupil.class_id.in_(teacher_class_ids), Pupil.is_active.is_(True))
    else:
        query = _apply_status_filter(query, filters.get('status', 'all'))

    query = _apply_common_filters(query, filters)
    pupils = query.order_by(SchoolClass.year_group, SchoolClass.name, Pupil.last_name, Pupil.first_name).all()

    pupil_ids = [pupil.id for pupil in pupils]
    latest_subject = _latest_subject_snapshots(pupil_ids)

    class_options_query = SchoolClass.query
    if current_user.is_teacher:
        class_options_query = class_options_query.filter(SchoolClass.teacher_id == current_user.id, SchoolClass.is_active.is_(True))
    class_options = class_options_query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    year_group_options = sorted({school_class.year_group for school_class in class_options})

    return render_template(
        'pupils/list.html',
        pupils=pupils,
        filters=filters,
        latest_subject=latest_subject,
        class_options=class_options,
        year_group_options=year_group_options,
    )


@pupils_bp.route('/<int:pupil_id>', methods=['GET', 'POST'])
@login_required
@teacher_or_admin_required
def profile(pupil_id: int):
    pupil = Pupil.query.join(Pupil.school_class).filter(Pupil.id == pupil_id).first_or_404()
    if not _can_view_pupil(pupil):
        abort(403)

    if request.method == 'POST':
        pupil.strengths_notes = request.form.get('strengths_notes', '').strip() or None
        pupil.next_steps_notes = request.form.get('next_steps_notes', '').strip() or None
        pupil.general_notes = request.form.get('general_notes', '').strip() or None
        db.session.add(pupil)
        db.session.commit()
        flash('Pupil notes saved.', 'success')
        return redirect(url_for('pupils.profile', pupil_id=pupil.id))

    subject_rows = SubjectResult.query.filter_by(pupil_id=pupil.id).order_by(SubjectResult.academic_year.desc(), SubjectResult.term.desc(), SubjectResult.updated_at.desc()).all()
    writing_rows = WritingResult.query.filter_by(pupil_id=pupil.id).order_by(WritingResult.academic_year.desc(), WritingResult.term.desc(), WritingResult.updated_at.desc()).all()
    phonics_rows = PhonicsScore.query.filter_by(pupil_id=pupil.id).all()
    times_tables_rows = TimesTableScore.query.filter_by(pupil_id=pupil.id).all()
    reception_rows = ReceptionTrackerEntry.query.filter_by(pupil_id=pupil.id).order_by(ReceptionTrackerEntry.academic_year.desc(), ReceptionTrackerEntry.tracking_point.desc()).all()
    sats_rows = SatsResult.query.filter_by(pupil_id=pupil.id).order_by(SatsResult.academic_year.desc(), SatsResult.assessment_point.desc()).all()
    sats_writing_rows = SatsWritingResult.query.filter_by(pupil_id=pupil.id).order_by(SatsWritingResult.academic_year.desc(), SatsWritingResult.assessment_point.desc()).all()
    sats_column_rows = (
        SatsColumnResult.query.filter_by(pupil_id=pupil.id)
        .join(SatsColumnResult.column)
        .order_by(SatsColumnResult.academic_year.desc(), SatsColumnResult.updated_at.desc())
        .all()
    )
    intervention_rows = Intervention.query.filter_by(pupil_id=pupil.id).order_by(Intervention.created_at.desc()).all()
    history_rows = PupilClassHistory.query.filter_by(pupil_id=pupil.id).order_by(PupilClassHistory.academic_year.desc()).all()

    latest_summary = _build_latest_summary(subject_rows, writing_rows)
    intervention_summary = {
        'total': len(intervention_rows),
        'active': len([row for row in intervention_rows if row.is_active]),
        'closed': len([row for row in intervention_rows if not row.is_active]),
    }
    latest_intervention_note = next((row.note for row in intervention_rows if row.note), None)
    active_focuses = sorted({row.subject for row in intervention_rows if row.is_active and row.subject})

    missing_data_warnings = []
    if not latest_summary.get('reading'):
        missing_data_warnings.append('Missing Reading result.')
    if not latest_summary.get('maths'):
        missing_data_warnings.append('Missing Maths result.')
    if not latest_summary.get('writing'):
        missing_data_warnings.append('Missing Writing judgement.')

    phonics_view_rows = [
        {
            'academic_year': row.academic_year,
            'column': row.test_column.name if row.test_column else 'Phonics test',
            'score': row.score,
        }
        for row in phonics_rows
    ]
    times_tables_view_rows = [
        {
            'academic_year': row.academic_year,
            'column': row.test_column.name if row.test_column else 'Times tables test',
            'score': row.score,
        }
        for row in times_tables_rows
    ]

    gap_rows = (
        GapScore.query.filter_by(pupil_id=pupil.id)
        .join(GapQuestion, GapScore.question_id == GapQuestion.id)
        .join(GapTemplate, GapQuestion.template_id == GapTemplate.id)
        .order_by(GapScore.updated_at.desc())
        .all()
    )

    return render_template(
        'pupils/profile.html',
        pupil=pupil,
        can_archive=_can_archive_pupil(pupil),
        can_restore=current_user.is_admin and not pupil.is_active,
        latest_summary=latest_summary,
        subject_rows=subject_rows,
        writing_rows=writing_rows,
        phonics_rows=phonics_view_rows,
        times_tables_rows=times_tables_view_rows,
        reception_rows=reception_rows,
        sats_rows=sats_rows,
        sats_writing_rows=sats_writing_rows,
        sats_column_rows=sats_column_rows,
        intervention_rows=intervention_rows,
        intervention_summary=intervention_summary,
        latest_intervention_note=latest_intervention_note,
        active_focuses=active_focuses,
        history_rows=history_rows,
        missing_data_warnings=missing_data_warnings,
        gap_rows=gap_rows,
    )


@pupils_bp.route('/<int:pupil_id>/archive', methods=['POST'])
@login_required
@teacher_or_admin_required
def archive(pupil_id: int):
    pupil = Pupil.query.join(Pupil.school_class).filter(Pupil.id == pupil_id).first_or_404()
    if not _can_archive_pupil(pupil):
        abort(403)
    if not pupil.is_active:
        flash(f'{pupil.full_name} is already archived.', 'info')
        return _redirect_to_pupil_source(pupil.id)

    pupil.is_active = False
    db.session.add(pupil)
    db.session.commit()
    flash(f'{pupil.full_name} has been archived.', 'success')
    return _redirect_to_pupil_source(pupil.id)


@pupils_bp.route('/<int:pupil_id>/restore', methods=['POST'])
@login_required
@teacher_or_admin_required
def restore(pupil_id: int):
    pupil = Pupil.query.join(Pupil.school_class).filter(Pupil.id == pupil_id).first_or_404()
    if not current_user.is_admin:
        abort(403)
    if pupil.is_active:
        flash(f'{pupil.full_name} is already active.', 'info')
        return _redirect_to_pupil_source(pupil.id)

    pupil.is_active = True
    db.session.add(pupil)
    db.session.commit()
    flash(f'{pupil.full_name} has been restored to active lists.', 'success')
    return _redirect_to_pupil_source(pupil.id)


def _build_pupil_filters(args) -> dict:
    return {
        'search': (args.get('search') or '').strip(),
        'class_id': (args.get('class_id') or '').strip(),
        'year_group': (args.get('year_group') or '').strip(),
        'gender': (args.get('gender') or 'all').strip() or 'all',
        'pp': (args.get('pp') or 'all').strip() or 'all',
        'laps': (args.get('laps') or 'all').strip() or 'all',
        'service_child': (args.get('service_child') or 'all').strip() or 'all',
        'send_flag': (args.get('send_flag') or 'all').strip() or 'all',
        'status': (args.get('status') or 'all').strip() or 'all',
    }


def _apply_common_filters(query, filters: dict):
    if filters.get('class_id') and filters['class_id'].isdigit():
        query = query.filter(Pupil.class_id == int(filters['class_id']))
    if filters.get('year_group') and filters['year_group'].isdigit():
        query = query.filter(SchoolClass.year_group == int(filters['year_group']))

    gender = filters.get('gender')
    if gender and gender != 'all':
        query = query.filter(func.lower(Pupil.gender) == gender.lower())

    for key, field in (
        ('pp', Pupil.pupil_premium),
        ('laps', Pupil.laps),
        ('service_child', Pupil.service_child),
    ):
        value = filters.get(key)
        if value == 'yes':
            query = query.filter(field.is_(True))
        elif value == 'no':
            query = query.filter(field.is_(False))

    search = filters.get('search', '')
    if search:
        lowered = search.lower()
        term = f'%{lowered}%'
        query = query.filter(
            or_(
                func.lower(Pupil.first_name).like(term),
                func.lower(Pupil.last_name).like(term),
                func.lower(Pupil.first_name + ' ' + Pupil.last_name).like(term),
            )
        )
    return query


def _apply_status_filter(query, status: str):
    normalized = (status or 'all').lower()
    if normalized in {'current', 'active'}:
        return query.filter(Pupil.is_active.is_(True))
    if normalized == 'archived':
        return query.filter(Pupil.is_active.is_(False))
    if normalized == 'previous':
        return query.filter(Pupil.is_active.is_(True), Pupil.class_history.any())
    return query


def _can_view_pupil(pupil: Pupil) -> bool:
    if current_user.is_admin:
        return True
    teacher_class_ids = {school_class.id for school_class in current_user.classes.filter_by(is_active=True).all()}
    return pupil.is_active and pupil.class_id in teacher_class_ids


def _can_archive_pupil(pupil: Pupil) -> bool:
    if current_user.is_admin:
        return True
    teacher_class_ids = {school_class.id for school_class in current_user.classes.filter_by(is_active=True).all()}
    return pupil.class_id in teacher_class_ids


def _redirect_to_pupil_source(pupil_id: int):
    next_url = (request.form.get('next') or '').strip()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('pupils.profile', pupil_id=pupil_id))


def _term_rank(term: str) -> int:
    mapping = {'autumn': 1, 'spring': 2, 'summer': 3}
    return mapping.get((term or '').lower(), 0)


def _latest_subject_snapshots(pupil_ids: list[int]) -> dict[int, dict]:
    if not pupil_ids:
        return {}
    snapshots: dict[int, dict] = defaultdict(dict)

    for result in SubjectResult.query.filter(SubjectResult.pupil_id.in_(pupil_ids), SubjectResult.subject.in_(['reading', 'maths'])).all():
        existing = snapshots[result.pupil_id].get(result.subject)
        result_key = (result.academic_year, _term_rank(result.term), result.updated_at)
        if not existing or result_key > existing['key']:
            snapshots[result.pupil_id][result.subject] = {'band': result.band_label, 'key': result_key}

    for result in WritingResult.query.filter(WritingResult.pupil_id.in_(pupil_ids)).all():
        existing = snapshots[result.pupil_id].get('writing')
        result_key = (result.academic_year, _term_rank(result.term), result.updated_at)
        if not existing or result_key > existing['key']:
            snapshots[result.pupil_id]['writing'] = {'band': result.band, 'key': result_key}

    flattened: dict[int, dict] = {}
    for pupil_id, subject_map in snapshots.items():
        flattened[pupil_id] = {subject: payload['band'] for subject, payload in subject_map.items()}
    return flattened


def _build_latest_summary(subject_rows: list[SubjectResult], writing_rows: list[WritingResult]) -> dict:
    latest_by_subject: dict[str, SubjectResult] = {}
    previous_by_subject: dict[str, SubjectResult] = {}

    ordered_subject_rows = sorted(subject_rows, key=lambda row: (row.academic_year, _term_rank(row.term), row.updated_at), reverse=True)
    for row in ordered_subject_rows:
        bucket = latest_by_subject if row.subject not in latest_by_subject else previous_by_subject
        if row.subject not in bucket:
            bucket[row.subject] = row

    ordered_writing = sorted(writing_rows, key=lambda row: (row.academic_year, _term_rank(row.term), row.updated_at), reverse=True)
    latest_writing = ordered_writing[0] if ordered_writing else None
    previous_writing = ordered_writing[1] if len(ordered_writing) > 1 else None

    summary = {}
    for subject in ['reading', 'maths', 'spag']:
        latest = latest_by_subject.get(subject)
        previous = previous_by_subject.get(subject)
        summary[subject] = _summary_payload(latest.band_label if latest else None, previous.band_label if previous else None)

    summary['writing'] = _summary_payload(latest_writing.band if latest_writing else None, previous_writing.band if previous_writing else None)

    available_ranks = [payload['rank'] for payload in summary.values() if payload.get('rank')]
    previous_ranks = [payload['previous_rank'] for payload in summary.values() if payload.get('previous_rank')]
    overall_rank = round(sum(available_ranks) / len(available_ranks), 2) if available_ranks else None
    previous_rank = round(sum(previous_ranks) / len(previous_ranks), 2) if previous_ranks else None
    summary['overall'] = _summary_payload(_rank_to_band(overall_rank), _rank_to_band(previous_rank))
    return summary


def _summary_payload(current_band: str | None, previous_band: str | None) -> dict:
    current_rank = BAND_RANK.get(current_band) if current_band else None
    previous_rank = BAND_RANK.get(previous_band) if previous_band else None
    delta = None
    direction = 'same'
    if current_rank is not None and previous_rank is not None:
        delta = current_rank - previous_rank
        if delta > 0:
            direction = 'up'
        elif delta < 0:
            direction = 'down'
    arrow = {'up': '↑', 'same': '→', 'down': '↓'}[direction]
    delta_label = f"{delta:+.0f}" if delta is not None else '0'
    return {
        'band': current_band,
        'previous_band': previous_band,
        'rank': current_rank,
        'previous_rank': previous_rank,
        'direction': direction,
        'arrow': arrow,
        'delta_label': delta_label,
        'band_theme': BAND_THEME.get(current_band or '', 'secondary'),
        'progress_theme': {'up': 'success', 'same': 'warning', 'down': 'danger'}[direction],
    }


def _rank_to_band(rank: float | None) -> str | None:
    if rank is None:
        return None
    if rank < 1.5:
        return 'Working Towards'
    if rank < 2.5:
        return 'On Track'
    return 'Exceeding'
