"""Teacher assessment entry routes."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Pupil, SubjectResult, WritingResult
from app.services import (
    SORT_OPTIONS,
    TERMS,
    WRITING_BAND_CHOICES,
    build_academic_year_options,
    compute_subject_result_values,
    format_subject_name,
    get_current_academic_year,
    get_current_term,
    get_subject_setting,
)
from app.services.assessments import AssessmentValidationError
from app.utils import get_primary_class_for_user, teacher_required

from . import teacher_bp


SUBJECT_META = {
    'maths': {'title': 'Maths'},
    'reading': {'title': 'Reading'},
    'spag': {'title': 'SPaG'},
    'writing': {'title': 'Writing'},
}


@teacher_bp.route('/maths', methods=['GET', 'POST'])
@login_required
@teacher_required
def maths():
    return render_subject_page('maths')


@teacher_bp.route('/reading', methods=['GET', 'POST'])
@login_required
@teacher_required
def reading():
    return render_subject_page('reading')


@teacher_bp.route('/spag', methods=['GET', 'POST'])
@login_required
@teacher_required
def spag():
    return render_subject_page('spag')


@teacher_bp.route('/writing', methods=['GET', 'POST'])
@login_required
@teacher_required
def writing():
    return render_writing_page()


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value == '':
        return None
    return int(value)


def _sort_subject_rows(rows: list[dict], sort_key: str) -> list[dict]:
    if sort_key == 'name_desc':
        return sorted(rows, key=lambda row: (row['pupil'].last_name.lower(), row['pupil'].first_name.lower()), reverse=True)
    if sort_key == 'percent_desc':
        return sorted(rows, key=lambda row: (row['combined_percent'] is None, -(row['combined_percent'] or 0), row['pupil'].last_name.lower()))
    if sort_key == 'percent_asc':
        return sorted(rows, key=lambda row: (row['combined_percent'] is None, row['combined_percent'] or 0, row['pupil'].last_name.lower()))
    if sort_key == 'band_asc':
        return sorted(rows, key=lambda row: ((row.get('band_display') or 'ZZZ'), row['pupil'].last_name.lower(), row['pupil'].first_name.lower()))
    return sorted(rows, key=lambda row: (row['pupil'].last_name.lower(), row['pupil'].first_name.lower(), row['pupil'].id))


def _filter_pupils(pupils: list[Pupil], search: str) -> list[Pupil]:
    if not search:
        return pupils
    search_value = search.lower()
    return [pupil for pupil in pupils if search_value in pupil.full_name.lower()]


def _base_subject_context(subject_key: str) -> dict:
    school_class = get_primary_class_for_user(current_user)
    current_year = get_current_academic_year()
    academic_year = request.values.get('academic_year', current_year)
    term = request.values.get('term', get_current_term())
    search = request.values.get('search', '').strip()
    sort = request.values.get('sort', 'name_asc')
    pupils = school_class.pupils.filter_by(is_active=True).all() if school_class else []
    pupils = _filter_pupils(pupils, search)
    return {
        'subject_key': subject_key,
        'page_title': SUBJECT_META[subject_key]['title'],
        'school_class': school_class,
        'current_year': current_year,
        'academic_year': academic_year,
        'term': term,
        'search': search,
        'sort': sort,
        'pupils': pupils,
        'academic_year_options': build_academic_year_options(academic_year),
        'sort_options': {
            key: label
            for key, label in SORT_OPTIONS.items()
            if key in {'name_asc', 'name_desc', 'percent_desc', 'percent_asc'}
        },
        'terms': TERMS,
    }


def render_subject_page(subject_key: str):
    """Render and save spreadsheet-style subject pages for score-based subjects."""

    context = _base_subject_context(subject_key)
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/subject_scores.html', rows=[], setting=None, **context)

    setting = get_subject_setting(school_class.year_group, subject_key, context['term'])
    result_rows = (
        SubjectResult.query.join(SubjectResult.pupil)
        .filter(
            SubjectResult.subject == subject_key,
            SubjectResult.academic_year == context['academic_year'],
            SubjectResult.term == context['term'],
            SubjectResult.pupil.has(class_id=school_class.id),
        )
        .all()
    )
    existing_by_pupil = {result.pupil_id: result for result in result_rows}
    rows = []

    if request.method == 'POST':
        errors: list[str] = []
        for pupil in context['pupils']:
            paper_1_raw = request.form.get(f'paper_1_score_{pupil.id}', '')
            paper_2_raw = request.form.get(f'paper_2_score_{pupil.id}', '')
            notes = request.form.get(f'notes_{pupil.id}', '').strip()
            existing = existing_by_pupil.get(pupil.id)
            row = {
                'pupil': pupil,
                'paper_1_score': paper_1_raw.strip(),
                'paper_2_score': paper_2_raw.strip(),
                'notes': notes,
                'combined_score': existing.combined_score if existing else None,
                'combined_percent': existing.combined_percent if existing else None,
                'band_label': existing.band_label if existing else None,
                'source': existing.source if existing else None,
            }
            try:
                paper_1_score = _parse_int(paper_1_raw)
                paper_2_score = _parse_int(paper_2_raw)
                if paper_1_score is None and paper_2_score is None and not notes:
                    if existing:
                        db.session.delete(existing)
                    row.update({'combined_score': None, 'combined_percent': None, 'band_label': None, 'source': None})
                else:
                    computed = compute_subject_result_values(setting, paper_1_score, paper_2_score)
                    result = existing or SubjectResult(
                        pupil_id=pupil.id,
                        academic_year=context['academic_year'],
                        term=context['term'],
                        subject=subject_key,
                    )
                    result.paper_1_score = paper_1_score
                    result.paper_2_score = paper_2_score
                    result.combined_score = computed['combined_score']
                    result.combined_percent = computed['combined_percent']
                    result.band_label = computed['band_label']
                    result.source = 'manual'
                    result.notes = notes or None
                    db.session.add(result)
                    row.update({
                        'paper_1_score': '' if paper_1_score is None else paper_1_score,
                        'paper_2_score': '' if paper_2_score is None else paper_2_score,
                        'combined_score': result.combined_score,
                        'combined_percent': result.combined_percent,
                        'band_label': result.band_label,
                        'source': result.source,
                    })
            except ValueError:
                errors.append(f'{pupil.full_name}: scores must be whole numbers.')
            except AssessmentValidationError as exc:
                errors.append(f'{pupil.full_name}: {exc}')
            rows.append(row)

        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, 'danger')
        else:
            db.session.commit()
            flash(f'{format_subject_name(subject_key)} results saved for {school_class.name}.', 'success')
            return redirect(
                url_for(
                    f'teacher.{subject_key}',
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['search'],
                    sort=context['sort'],
                )
            )
    else:
        for pupil in context['pupils']:
            existing = existing_by_pupil.get(pupil.id)
            rows.append(
                {
                    'pupil': pupil,
                    'paper_1_score': '' if not existing or existing.paper_1_score is None else existing.paper_1_score,
                    'paper_2_score': '' if not existing or existing.paper_2_score is None else existing.paper_2_score,
                    'combined_score': existing.combined_score if existing else None,
                    'combined_percent': existing.combined_percent if existing else None,
                    'band_label': existing.band_label if existing else None,
                    'notes': existing.notes if existing else '',
                    'source': existing.source if existing else None,
                }
            )

    rows = _sort_subject_rows(rows, context['sort'])
    return render_template('teacher/subject_scores.html', rows=rows, setting=setting, **context)


def render_writing_page():
    """Render and save the spreadsheet-style writing page."""

    context = _base_subject_context('writing')
    context['sort_options'] = {
        key: label
        for key, label in SORT_OPTIONS.items()
        if key in {'name_asc', 'name_desc', 'band_asc'}
    }
    school_class = context['school_class']
    if not school_class:
        flash('No active class is assigned to your account yet.', 'warning')
        return render_template('teacher/writing_results.html', rows=[], writing_band_choices=WRITING_BAND_CHOICES, **context)

    result_rows = (
        WritingResult.query.join(WritingResult.pupil)
        .filter(
            WritingResult.academic_year == context['academic_year'],
            WritingResult.term == context['term'],
            WritingResult.pupil.has(class_id=school_class.id),
        )
        .all()
    )
    existing_by_pupil = {result.pupil_id: result for result in result_rows}
    rows = []

    if request.method == 'POST':
        errors: list[str] = []
        for pupil in context['pupils']:
            band = request.form.get(f'band_{pupil.id}', '').strip()
            notes = request.form.get(f'notes_{pupil.id}', '').strip()
            existing = existing_by_pupil.get(pupil.id)
            row = {'pupil': pupil, 'band': band, 'notes': notes}
            if band and band not in dict(WRITING_BAND_CHOICES):
                errors.append(f'{pupil.full_name}: invalid writing band selected.')
                rows.append(row)
                continue

            if not band and not notes:
                if existing:
                    db.session.delete(existing)
            elif not band:
                errors.append(f'{pupil.full_name}: choose a writing band before saving notes.')
            else:
                result = existing or WritingResult(
                    pupil_id=pupil.id,
                    academic_year=context['academic_year'],
                    term=context['term'],
                    band=band,
                )
                result.band = band
                result.notes = notes or None
                db.session.add(result)
                row['band'] = result.band
            rows.append(row)

        if errors:
            db.session.rollback()
            for error in errors:
                flash(error, 'danger')
        else:
            db.session.commit()
            flash(f'Writing results saved for {school_class.name}.', 'success')
            return redirect(
                url_for(
                    'teacher.writing',
                    academic_year=context['academic_year'],
                    term=context['term'],
                    search=context['search'],
                    sort=context['sort'],
                )
            )
    else:
        for pupil in context['pupils']:
            existing = existing_by_pupil.get(pupil.id)
            rows.append({'pupil': pupil, 'band': existing.band if existing else '', 'notes': existing.notes if existing else ''})

    for row in rows:
        row['band_display'] = dict(WRITING_BAND_CHOICES).get(row.get('band'), '—')
    rows = _sort_subject_rows(rows, context['sort'])
    return render_template('teacher/writing_results.html', rows=rows, writing_band_choices=WRITING_BAND_CHOICES, **context)
