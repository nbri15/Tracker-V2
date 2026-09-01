"""Dashboard routing for role-aware landing pages."""

from datetime import datetime, timezone

from flask import current_app, flash, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from weasyprint import HTML

from app.models import AcademicYear, Intervention, Pupil, SatsResult, SchoolClass, SimpleSatsExamTab, SimpleSatsSetting, SubjectResult, User, WritingResult
from app.services import (
    BOOLEAN_FILTER_CHOICES,
    CLASS_SORT_OPTIONS,
    build_admin_pupil_filter_state,
    apply_admin_pupil_filters,
    build_class_overview_rows,
    build_dashboard_summary,
    build_subject_overview_cards,
    calculate_progress,
    get_current_academic_year,
    get_school_working_academic_year,
    get_selected_current_academic_year,
    get_selected_academic_year,
    build_academic_year_options,
    get_dashboard_stats,
    get_class_pupil_query,
    get_gender_filter_options,
    get_tracker_mode,
    get_tracker_mode_label,
    is_academic_year_rollover_due,
    sort_class_rows,
)
from app.utils import (
    admin_required,
    current_school_id,
    demo_filter_classes,
    demo_filter_pupils,
    get_primary_class_for_user,
    school_scoped_query,
    get_year_group_class_for_user,
    teacher_required,
    safe_redirect_target,
)

from . import dashboards_bp


@dashboards_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))
    return render_template('public_home.html')




@dashboards_bp.route('/set-academic-year', methods=['POST'])
@login_required
def set_academic_year():
    year_id = request.form.get('academic_year_id') or request.form.get('year')
    try:
        year = AcademicYear.query.get(int(year_id))
    except (TypeError, ValueError):
        year = None
    if year is None:
        flash('Academic year could not be found.', 'danger')
    else:
        session['selected_academic_year_id'] = year.id
        flash(f'Academic year set to {year.name}', 'success')
    return redirect(safe_redirect_target(request.referrer, url_for('dashboards.index')))

@dashboards_bp.route('/dashboard')
@login_required
def index():
    if current_user.is_executive_admin:
        return redirect(url_for('executive.schools'))
    if current_user.can_manage_school:
        return redirect(url_for('dashboards.admin_dashboard'))
    return redirect(url_for('dashboards.teacher_dashboard'))


@dashboards_bp.route('/dashboard/teacher')
@login_required
@teacher_required
def teacher_dashboard():
    term = (request.args.get("term") or "Summer").strip()
    if term not in ("Autumn", "Spring", "Summer", "All"):
        term = "Summer"

    school_class = get_primary_class_for_user(current_user)
    school_id = current_school_id()
    working_year = get_school_working_academic_year(school_id)
    has_explicit_year = bool(request.args.get('year') or request.args.get('academic_year'))
    selected_year = (
        get_selected_academic_year(request.args.get('year'), request.args.get('academic_year'))
        if has_explicit_year
        else working_year
    )
    academic_year = selected_year.name
    pupil_count = get_class_pupil_query(school_class, academic_year).filter(Pupil.is_active.is_(True)).count() if school_class else 0
    summary_rows = get_dashboard_stats(school_class.id if school_class else None, academic_year)
    active_interventions = (
        Intervention.query.join(Intervention.pupil)
        .filter(
            Intervention.is_active.is_(True),
            Intervention.academic_year == academic_year,
            Pupil.class_id == school_class.id,
            Pupil.is_active.is_(True),
            Pupil.is_demo.is_(school_class.is_demo),
            Intervention.is_demo.is_(school_class.is_demo),
        )
        .options(joinedload(Intervention.pupil))
        .order_by(Pupil.last_name, Pupil.first_name)
        .all()
        if school_class
        else []
    )

    context = {
        'school_class': school_class,
        'has_year6_sats_access': get_year_group_class_for_user(current_user, 6) is not None,
        'pupil_count': pupil_count,
        'academic_year': academic_year,
        'selected_year': selected_year,
        'academic_year_options': build_academic_year_options(academic_year),
        'term': term,
        'term_label': 'All terms' if term == 'All' else term,
        'summary_rows': summary_rows,
        'chart_cards': summary_rows,
        'active_interventions': active_interventions,
        'tracker_mode': get_tracker_mode(school_class.year_group) if school_class else 'normal',
        'tracker_mode_label': get_tracker_mode_label(school_class.year_group) if school_class else 'Usual tracker',
        'selected_term': term,
        'term_choices': ['Autumn', 'Spring', 'Summer', 'All'],
    }
    return render_template('dashboards/teacher_dashboard.html', **context)


@dashboards_bp.route('/dashboard/admin')
@login_required
@admin_required
def admin_dashboard():
    if current_user.is_executive_admin and current_school_id() is None:
        return redirect(url_for('executive.schools'))
    school_id = current_school_id()
    working_year = get_school_working_academic_year(school_id)
    has_explicit_year = bool(request.args.get('year') or request.args.get('academic_year'))
    selected_year = (
        get_selected_academic_year(request.args.get('year'), request.args.get('academic_year'))
        if has_explicit_year
        else working_year
    )
    academic_year = selected_year.name
    calendar_year = get_current_academic_year()
    term = (request.args.get("term") or "Summer").strip()
    if term not in ("Autumn", "Spring", "Summer", "All"):
        term = "Summer"
    selected_term = term
    term_filter = term.lower()
    filter_year_group = request.args.get('year_group', '').strip()
    filter_teacher = request.args.get('teacher_id', '').strip()
    filter_class = request.args.get('class_id', '').strip()
    sort = request.args.get('sort', 'year_group')
    pupil_filters = build_admin_pupil_filter_state(request.args)

    query = demo_filter_classes(SchoolClass.query.filter_by(is_active=True))
    if filter_year_group:
        query = query.filter(SchoolClass.year_group == int(filter_year_group))
    if filter_teacher:
        query = query.filter(SchoolClass.teacher_id == int(filter_teacher))
    if filter_class:
        query = query.filter(SchoolClass.id == int(filter_class))

    classes = query.options(joinedload(SchoolClass.teacher)).order_by(SchoolClass.year_group, SchoolClass.name).all()
    class_rows = build_class_overview_rows(classes, academic_year, filters=pupil_filters, term=term_filter)
    class_rows = sort_class_rows(class_rows, sort)
    subject_cards = build_subject_overview_cards(class_rows)
    teacher_options = school_scoped_query(User, User.query.filter_by(role='teacher', is_active=True, is_demo=current_user.is_demo)).order_by(User.username).all()
    class_options = demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).order_by(SchoolClass.year_group, SchoolClass.name).all()
    year6_overview = {}

    context = {
        'academic_year': academic_year,
        'working_academic_year': working_year.name,
        'calendar_academic_year': calendar_year,
        'rollover_required': is_academic_year_rollover_due(working_year.name, calendar_year),
        'selected_year': selected_year,
        'academic_year_options': build_academic_year_options(academic_year),
        'term': term,
        'selected_term': selected_term,
        'term_choices': ['Autumn', 'Spring', 'Summer', 'All'],
        'term_label': 'All terms' if term == 'All' else term,
        'total_pupils': demo_filter_pupils(Pupil.query.filter_by(is_active=True)).count(),
        'total_classes': demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).count(),
        'teacher_count': school_scoped_query(User, User.query.filter_by(role='teacher', is_active=True, is_demo=current_user.is_demo)).count(),
        'filtered_pupil_total': sum(row['pupil_count'] for row in class_rows),
        'filtered_class_count': len(class_rows),
        'class_rows': class_rows,
        'subject_cards': subject_cards,
        'filter_year_group': filter_year_group,
        'filter_teacher': filter_teacher,
        'filter_class': filter_class,
        'pupil_filters': pupil_filters,
        'boolean_filter_choices': BOOLEAN_FILTER_CHOICES,
        'gender_options': get_gender_filter_options(class_id=int(filter_class)) if filter_class else get_gender_filter_options(),
        'sort': sort,
        'sort_options': CLASS_SORT_OPTIONS,
        'teacher_options': teacher_options,
        'class_options': class_options,
        'year6_overview': year6_overview,
        'year6_tracker_mode_label': get_tracker_mode_label(6),
    }
    return render_template('dashboards/admin_dashboard.html', **context)


from app.extensions import db

SATS_SIMPLE_FIELDS = ['arithmetic_score', 'reasoning_1_score', 'reasoning_2_score', 'maths_scaled_score', 'reading_score', 'reading_scaled_score', 'spelling_score', 'grammar_score', 'spag_scaled_score', 'notes']


def _scaled_band(score: int | None) -> str:
    if score is None:
        return ''
    if score <= 99:
        return 'scaled-low'
    if score <= 110:
        return 'scaled-at'
    return 'scaled-high'


def _scaled_progress(current: int | None, previous: int | None) -> dict[str, str | int | None]:
    progress = calculate_progress(current, previous)
    theme = progress.get('theme')
    class_name = 'progress-none' if theme is None else f'progress-{theme}'
    return {'delta': progress.get('delta'), 'label': progress.get('label') or '—', 'class': class_name}


def _ensure_simple_tabs_and_settings(academic_year: str, school_id: int):
    tabs = SimpleSatsExamTab.query.filter_by(school_id=school_id, academic_year=academic_year).order_by(SimpleSatsExamTab.display_order).all()
    if not tabs:
        for n in range(1, 5):
            db.session.add(SimpleSatsExamTab(school_id=school_id, academic_year=academic_year, exam_number=n, name=f'Exam {n}', display_order=n, is_active=True))
            db.session.add(SimpleSatsSetting(school_id=school_id, academic_year=academic_year, exam_number=n))
        db.session.commit()
        tabs = SimpleSatsExamTab.query.filter_by(school_id=school_id, academic_year=academic_year).order_by(SimpleSatsExamTab.display_order).all()
    return tabs

@dashboards_bp.route('/sats/simple')
@login_required
def sats_simple():
    school_id = current_school_id()
    if school_id is None:
        return redirect(url_for('executive.schools'))
    selected_year = get_selected_academic_year(request.args.get('year'), request.args.get('academic_year'))
    academic_year = selected_year.name
    term = (request.args.get('term', 'all') or 'all').strip().lower()
    if term not in {'all', 'autumn', 'spring', 'summer'}:
        term = 'all'
    exam_number = int((request.args.get('exam_number') or '1'))
    tabs = _ensure_simple_tabs_and_settings(academic_year, school_id)
    allowed_exam_numbers = {tab.exam_number for tab in tabs if tab.is_active}
    if exam_number not in allowed_exam_numbers:
        exam_number = tabs[0].exam_number if tabs else 1
    class_id = request.args.get('class_id', '').strip()
    base = demo_filter_classes(SchoolClass.query.filter_by(year_group=6, is_active=True))
    class_options = base.order_by(SchoolClass.name).all()
    if current_user.is_teacher and not current_user.can_manage_school:
        school_class = get_year_group_class_for_user(current_user, 6)
        if not school_class:
            return redirect(url_for('dashboards.teacher_dashboard'))
        class_options = [school_class]
        selected_class = school_class
    else:
        selected_class = next((c for c in class_options if str(c.id)==class_id), class_options[0] if class_options else None)
    pupils=[]
    if selected_class:
        pupils = (
            demo_filter_pupils(Pupil.query)
            .join(SchoolClass, Pupil.class_id == SchoolClass.id)
            .filter(
                Pupil.school_id == school_id,
                Pupil.class_id == selected_class.id,
                Pupil.is_active.is_(True),
                SchoolClass.year_group == 6,
            )
            .order_by(Pupil.last_name, Pupil.first_name)
            .all()
        )
    pupil_ids=[p.id for p in pupils]
    result_map={}
    scores_by_pupil_exam = {}
    if pupil_ids:
        all_rows = SatsResult.query.filter(
            SatsResult.school_id == school_id,
            SatsResult.academic_year == academic_year,
            SatsResult.pupil_id.in_(pupil_ids),
        ).all()
        for row in all_rows:
            scores_by_pupil_exam.setdefault(row.pupil_id, {})[row.exam_number] = row
        rows = [r for r in all_rows if r.exam_number == exam_number]
        result_map={r.pupil_id:r for r in rows}
    settings = {row.exam_number: row for row in SimpleSatsSetting.query.filter_by(school_id=school_id, academic_year=academic_year).all()}
    return render_template('sats_simple.html', academic_year=academic_year, selected_year=selected_year, academic_year_options=build_academic_year_options(academic_year), exam_number=exam_number, pupils=pupils, result_map=result_map, class_options=class_options, selected_class=selected_class, settings=settings, tabs=tabs, scores_by_pupil_exam=scores_by_pupil_exam, scaled_band= _scaled_band, scaled_progress=_scaled_progress)

@dashboards_bp.route('/api/sats/simple/quick-save', methods=['POST'])
@login_required
def sats_simple_quick_save():
    data=request.get_json(silent=True) or request.form
    school_id = current_school_id()
    if school_id is None:
        return {'ok': False, 'error': 'Select a school before editing SATs'}, 403
    try:
        pupil_id = int(data.get('pupil_id'))
        exam_number = int(data.get('exam_number'))
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'Invalid pupil or exam reference'}, 400
    field=str(data.get('field'))
    value_raw=data.get('value')
    if field not in SATS_SIMPLE_FIELDS:
        return {'ok':False,'error':'Invalid payload'},400
    pupil=(
        demo_filter_pupils(Pupil.query)
        .join(SchoolClass, Pupil.class_id == SchoolClass.id)
        .filter(
            Pupil.id == pupil_id,
            Pupil.is_active.is_(True),
            Pupil.school_id == school_id,
            SchoolClass.year_group == 6,
        )
        .first()
    )
    if not pupil or pupil.school_id != school_id:
        return {'ok':False,'error':'Forbidden'},403
    academic_year=str(data.get('academic_year') or get_selected_current_academic_year())
    rec=SatsResult.query.filter_by(school_id=school_id,pupil_id=pupil_id,academic_year=academic_year,exam_number=exam_number).first()
    if not rec:
        rec=SatsResult(school_id=school_id,pupil_id=pupil_id,academic_year=academic_year,exam_number=exam_number,subject='maths',assessment_point=exam_number,is_most_recent=False)
        db.session.add(rec)
    setattr(rec, field, value_raw.strip() if field == 'notes' and str(value_raw).strip() != '' else (int(value_raw) if str(value_raw).strip()!='' else None))
    a,b,c=rec.arithmetic_score or 0, rec.reasoning_1_score or 0, rec.reasoning_2_score or 0
    s,g=rec.spelling_score or 0, rec.grammar_score or 0
    rec.maths_combined_score=a+b+c
    rec.spag_combined_score=s+g
    db.session.commit()
    prev = None
    if exam_number > 1:
        prev = SatsResult.query.filter_by(
            school_id=school_id,
            pupil_id=pupil_id,
            academic_year=academic_year,
            exam_number=exam_number - 1,
        ).first()
    payload = {
        'ok': True,
        'maths_combined_score': rec.maths_combined_score,
        'spag_combined_score': rec.spag_combined_score,
    }
    for key in ['maths_scaled_score', 'reading_scaled_score', 'spag_scaled_score']:
        current_score = getattr(rec, key)
        prev_score = getattr(prev, key) if prev else None
        payload[key] = {
            'score': current_score,
            'color_class': _scaled_band(current_score),
            'progress': _scaled_progress(current_score, prev_score),
        }
    return payload


@dashboards_bp.route('/api/sats/simple/add-exam', methods=['POST'])
@login_required
def sats_simple_add_exam():
    school_id = current_school_id()
    if school_id is None:
        return {'ok': False, 'error': 'Select a school before editing SATs'}, 403
    academic_year = str((request.get_json(silent=True) or {}).get('academic_year') or get_selected_current_academic_year())
    tabs = _ensure_simple_tabs_and_settings(academic_year, school_id)
    next_exam = max([tab.exam_number for tab in tabs], default=0) + 1
    db.session.add(SimpleSatsExamTab(school_id=school_id, academic_year=academic_year, exam_number=next_exam, name=f'Exam {next_exam}', display_order=next_exam, is_active=True))
    db.session.add(SimpleSatsSetting(school_id=school_id, academic_year=academic_year, exam_number=next_exam))
    db.session.commit()
    return {'ok': True, 'exam_number': next_exam}


@dashboards_bp.route('/api/sats/simple/settings', methods=['POST'])
@dashboards_bp.route('/api/sats/settings/quick-save', methods=['POST'])
@login_required
def sats_simple_save_settings():
    data = request.get_json(silent=True) or request.form
    school_id = current_school_id()
    if school_id is None:
        return {'ok': False, 'error': 'Select a school before editing SATs'}, 403
    academic_year = str(data.get('academic_year') or get_selected_current_academic_year())
    exam_number = int(data.get('exam_number') or data.get('record_id') or 0)
    if exam_number < 1:
        return {'ok': False, 'error': 'Invalid exam'}, 400
    settings = SimpleSatsSetting.query.filter_by(school_id=school_id, academic_year=academic_year, exam_number=exam_number).first()
    if not settings:
        settings = SimpleSatsSetting(school_id=school_id, academic_year=academic_year, exam_number=exam_number)
    allowed = ['arithmetic_max', 'reasoning_1_max', 'reasoning_2_max', 'reading_max', 'spelling_max', 'grammar_max']
    if data.get('field') in allowed:
        setattr(settings, data.get('field'), int(data.get('value') or 0))
    else:
        for field in allowed:
            setattr(settings, field, int(data.get(field) or getattr(settings, field)))
    settings.updated_at = datetime.now(timezone.utc)
    db.session.add(settings)
    db.session.commit()
    return {'ok': True}



YEAR_OVERVIEW_TERMS = ['autumn', 'spring', 'summer']
YEAR_OVERVIEW_BANDS = ['WT', 'ARE', 'EXS']


def _band_short(value):
    """Normalise tracker/result labels into the three yearly overview bands."""
    text = (value or '').strip().lower().replace('_', ' ').replace('-', ' ')
    if not text:
        return None
    if text in {'wt', 'wts', 'working towards', 'working towards are'} or 'towards' in text:
        return 'WT'
    if text in {'are', 'ot', 'on track', 'working at', 'working at are', 'working at are', 'working at age related expectations'} or 'on track' in text or 'working at' in text:
        return 'ARE'
    if text in {'exs', 'gds', 'exceeding', 'exceeding are', 'greater depth'} or 'exceed' in text or 'greater depth' in text:
        return 'EXS'
    return None


def _normalise_year_overview_subject(value: str | None) -> str:
    key = (value or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'maths': 'maths', 'mathematics': 'maths', 'reading': 'reading', 'read': 'reading',
        'spag': 'spag', 'spa_g': 'spag', 'spelling_grammar': 'spag',
        'spelling_punctuation_grammar': 'spag', 'grammar_punctuation_spelling': 'spag',
        'writing': 'writing',
    }
    return aliases.get(key, key)


def _normalise_year_overview_term(value: str | None) -> str | None:
    key = (value or '').strip().lower()
    if key in {'autumn', 'aut', 'a'}:
        return 'autumn'
    if key in {'spring', 'spr', 'sp', 's'}:
        return 'spring'
    if key in {'summer', 'sum', 'su'}:
        return 'summer'
    return None


def _latest_year_overview_row(rows):
    return sorted(rows, key=lambda row: ((row.updated_at.isoformat() if row.updated_at else ''), row.id or 0), reverse=True)[0] if rows else None


def _paper_labels(subject):
    return {
        'maths': ('Arithmetic', 'Reasoning'),
        'reading': ('Reading paper', 'Reading paper 2'),
        'spag': ('Spelling', 'Grammar'),
    }.get(subject, ('Paper 1', 'Paper 2'))


def _term_cell(*, band=None, percent=None, paper_1=None, paper_2=None, subject='maths'):
    label1, label2 = _paper_labels(subject)
    details = []
    if paper_1 is not None:
        details.append({'label': label1, 'score': paper_1})
    if paper_2 is not None:
        details.append({'label': label2, 'score': paper_2})
    return {'band': band, 'percent': percent, 'paper_1': paper_1, 'paper_2': paper_2, 'details': details, 'missing': band is None and percent is None}


def _format_percent(value):
    if value is None:
        return ''
    return f'{value:g}%'


def _progress_for_cells(cells):
    available = [(term, cells[term]) for term in YEAR_OVERVIEW_TERMS if cells[term].get('percent') is not None]
    bands = [(term, cells[term].get('band')) for term in YEAR_OVERVIEW_TERMS if cells[term].get('band')]
    if len(available) < 2:
        return {'has_data': False, 'label': 'Not enough data', 'delta': None, 'from_percent': None, 'to_percent': None, 'latest_percent': None, 'theme': 'neutral', 'milestone': ''}
    terms_with_percent = {term: cell for term, cell in available}
    if 'autumn' in terms_with_percent and 'summer' in terms_with_percent:
        first_term, latest_term = 'autumn', 'summer'
    elif 'spring' in terms_with_percent and 'summer' in terms_with_percent:
        first_term, latest_term = 'spring', 'summer'
    else:
        first_term, latest_term = available[0][0], available[-1][0]
    first = terms_with_percent[first_term]['percent']
    latest = terms_with_percent[latest_term]['percent']
    delta = round(latest - first, 1)
    if delta > 0:
        label = f'⬆ +{delta:g}%'; theme = 'positive'
    elif delta < 0:
        label = f'⬇ {delta:g}%'; theme = 'negative'
    else:
        label = '➜ Stable'; theme = 'neutral'
    start_band = next((cells[t].get('band') for t in YEAR_OVERVIEW_TERMS if cells[t].get('band')), None)
    latest_band = next((cells[t].get('band') for t in reversed(YEAR_OVERVIEW_TERMS) if cells[t].get('band')), None)
    available_bands = [band for _, band in bands]
    milestone = ''
    if delta < 0:
        milestone = '⚠ Declined'
    elif start_band == 'WT' and latest_band == 'EXS':
        milestone = '🚀 Outstanding progress'
    elif start_band == 'WT' and latest_band in {'ARE', 'EXS'}:
        milestone = '🎯 Reached ARE'
    elif start_band == 'ARE' and latest_band == 'EXS':
        milestone = '🚀 Moved to EXS'
    elif available_bands and all(b == 'EXS' for b in available_bands):
        milestone = '⭐ Consistently EXS'
    elif available_bands and all(b == 'WT' for b in available_bands):
        milestone = '🔴 Needs continued support' if len(available_bands) == len(YEAR_OVERVIEW_TERMS) else '➜ Still WT'
    elif delta == 0 and latest_band == 'ARE':
        milestone = '➜ Stable ARE'
    elif delta == 0 and latest_band == 'WT':
        milestone = '➜ Still WT'
    elif delta == 0 and latest_band == 'EXS':
        milestone = '⭐ Consistently EXS'
    return {'has_data': True, 'label': label, 'delta': delta, 'from_percent': first, 'to_percent': latest, 'latest_percent': latest, 'theme': theme, 'milestone': milestone, 'start_band': start_band, 'latest_band': latest_band, 'all_bands': available_bands}


def _sort_year_overview_rows(rows, sort_key):
    if sort_key == 'most_improved':
        return sorted(rows, key=lambda r: (r['progress']['delta'] is not None, r['progress']['delta'] or -999), reverse=True)
    if sort_key == 'biggest_decline':
        return sorted(rows, key=lambda r: (r['progress']['delta'] is None, r['progress']['delta'] if r['progress']['delta'] is not None else 999))
    if sort_key == 'reached_are':
        return sorted(rows, key=lambda r: not (r['progress'].get('start_band') == 'WT' and r['progress'].get('latest_band') in {'ARE', 'EXS'}))
    if sort_key == 'still_wt':
        return sorted(rows, key=lambda r: not (r['progress'].get('latest_band') == 'WT'))
    if sort_key == 'consistently_exs':
        return sorted(rows, key=lambda r: not (r['progress'].get('all_bands') and all(b == 'EXS' for b in r['progress']['all_bands'])))
    return sorted(rows, key=lambda r: (r['pupil'].last_name.lower(), r['pupil'].first_name.lower()))


def _class_year_overview_context():
    selected_year = get_selected_academic_year(request.args.get('year'), request.args.get('academic_year'))
    academic_year = selected_year.name
    subject = (request.args.get('subject') or 'maths').strip().lower()
    if subject not in {'maths', 'reading', 'spag', 'writing'}:
        subject = 'maths'
    sort = request.args.get('sort', 'name')
    if sort not in {'name', 'most_improved', 'biggest_decline', 'reached_are', 'still_wt', 'consistently_exs'}:
        sort = 'name'
    toggles = {
        'show_percentages': request.args.get('show_percentages', '1') != '0',
        'show_papers': request.args.get('show_papers', '0') == '1',
        'show_progress_bars': request.args.get('show_progress_bars', '1') != '0',
    }
    class_options_query = demo_filter_classes(SchoolClass.query.filter_by(is_active=True))
    if current_user.is_teacher and not current_user.can_manage_school:
        class_options_query = class_options_query.filter(SchoolClass.teacher_id == current_user.id)
    class_options = class_options_query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    selected_class_id = request.args.get('class_id', type=int)
    selected_class = next((c for c in class_options if c.id == selected_class_id), class_options[0] if class_options else None)
    filters = build_admin_pupil_filter_state(request.args)
    pupils = apply_admin_pupil_filters(get_class_pupil_query(selected_class, academic_year), filters).order_by(Pupil.last_name, Pupil.first_name).all() if selected_class else []
    pupil_ids = [p.id for p in pupils]
    result_map = {}
    if pupil_ids:
        if subject == 'writing':
            rows = WritingResult.query.filter(WritingResult.academic_year == academic_year, WritingResult.pupil_id.in_(pupil_ids), func.lower(WritingResult.term).in_(['autumn','aut','spring','spr','summer','sum'])).order_by(WritingResult.updated_at.desc(), WritingResult.id.desc()).all()
            grouped = {}
            for row in rows:
                term = _normalise_year_overview_term(row.term)
                if term in YEAR_OVERVIEW_TERMS:
                    grouped.setdefault((row.pupil_id, term), []).append(row)
            for key, grouped_rows in grouped.items():
                latest = _latest_year_overview_row(grouped_rows)
                result_map[key] = _term_cell(band=_band_short(latest.band), subject=subject)
        else:
            aliases = {'maths':['maths','mathematics'], 'reading':['reading','read'], 'spag':['spag','spa_g','spelling_grammar','spelling grammar','spelling_punctuation_grammar','spelling punctuation grammar','grammar_punctuation_spelling','grammar punctuation spelling']}[subject]
            rows = SubjectResult.query.filter(SubjectResult.academic_year == academic_year, SubjectResult.pupil_id.in_(pupil_ids), func.lower(SubjectResult.term).in_(['autumn','aut','spring','spr','summer','sum']), func.lower(SubjectResult.subject).in_(aliases)).order_by(SubjectResult.updated_at.desc(), SubjectResult.id.desc()).all()
            grouped = {}
            for row in rows:
                term = _normalise_year_overview_term(row.term)
                if term in YEAR_OVERVIEW_TERMS and _normalise_year_overview_subject(row.subject) == subject:
                    grouped.setdefault((row.pupil_id, term), []).append(row)
            for key, grouped_rows in grouped.items():
                latest = _latest_year_overview_row(grouped_rows)
                result_map[key] = _term_cell(band=_band_short(latest.band_label), percent=latest.combined_percent, paper_1=latest.paper_1_score, paper_2=latest.paper_2_score, subject=subject)
    child_rows=[]; counts={term:{band:0 for band in YEAR_OVERVIEW_BANDS} for term in YEAR_OVERVIEW_TERMS}
    for idx,p in enumerate(pupils, start=1):
        cells={term: result_map.get((p.id, term), _term_cell(subject=subject)) for term in YEAR_OVERVIEW_TERMS}
        for term, cell in cells.items():
            if cell.get('band') in counts[term]: counts[term][cell['band']] += 1
        child_rows.append({'pupil':p, 'anon_name':f'Pupil {idx}', 'cells':cells, 'progress':_progress_for_cells(cells)})
    child_rows = _sort_year_overview_rows(child_rows, sort)
    total=len(pupils)
    summary=[{'term':term.title(), 'key':term, 'bands':[{'band':band,'count':counts[term][band],'total':total,'percent':round((counts[term][band]/total)*100) if total else 0} for band in YEAR_OVERVIEW_BANDS]} for term in YEAR_OVERVIEW_TERMS]
    boolean_filter_options = [('all', 'All'), ('yes', 'Yes'), ('no', 'No')]
    return dict(selected_year=selected_year, academic_year=academic_year, academic_year_options=build_academic_year_options(academic_year), subject=subject, subject_options=[('maths','Maths'),('reading','Reading'),('spag','SPaG'),('writing','Writing')], class_options=class_options, selected_class=selected_class, filters=filters, gender_options=[('all','All'),('male','Male'),('female','Female')], pp_options=boolean_filter_options, send_options=boolean_filter_options, laps_options=boolean_filter_options, service_options=boolean_filter_options, rows=child_rows, summary=summary, terms=YEAR_OVERVIEW_TERMS, sort=sort, sort_options=[('name','Name'),('most_improved','Most Improved'),('biggest_decline','Biggest Decline'),('reached_are','Reached ARE'),('still_wt','Still WT'),('consistently_exs','Consistently EXS')], toggles=toggles)


def _download_year_overview(ctx, anonymised=False, as_pdf=False):
    subject_label = dict(ctx['subject_options']).get(ctx['subject'], ctx['subject'].title())
    title = f"{subject_label} class yearly overview - {ctx['academic_year']}"
    if as_pdf:
        headers = ['Pupil', 'Autumn', 'Spring', 'Summer', 'Progress']
        rows = []
        for r in ctx['rows']:
            def pdf_cell(term):
                c = r['cells'][term]; bits = [c.get('band') or 'Missing']
                if c.get('percent') is not None: bits.append(_format_percent(c['percent']))
                return ' '.join(bits)
            rows.append([(r['anon_name'] if anonymised else r['pupil'].full_name), pdf_cell('autumn'), pdf_cell('spring'), pdf_cell('summer'), f"{r['progress']['label']} {r['progress'].get('milestone') or ''}".strip()])
        html = render_template('exports/table_pdf.html', title=title, subtitle=ctx['selected_class'].name if ctx['selected_class'] else '', headers=headers, rows=rows, filters={'Academic year': ctx['academic_year'], 'Subject': subject_label}, anonymise=anonymised, generated_at=datetime.now(timezone.utc))
        pdf = HTML(string=html, base_url=request.url_root).write_pdf()
        resp = make_response(pdf); resp.headers['Content-Type']='application/pdf'; resp.headers['Content-Disposition']=f'attachment; filename=class-year-overview-{ctx["subject"]}.pdf'; return resp
    import csv, io
    headers = ['Pupil','Autumn Band','Autumn %','Autumn Paper 1','Autumn Paper 2','Spring Band','Spring %','Spring Paper 1','Spring Paper 2','Summer Band','Summer %','Summer Paper 1','Summer Paper 2','Progress %','Progress Label']
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(headers)
    for r in ctx['rows']:
        out=[r['anon_name'] if anonymised else r['pupil'].full_name]
        for term in YEAR_OVERVIEW_TERMS:
            c=r['cells'][term]; out += [c.get('band') or '', _format_percent(c.get('percent')), c.get('paper_1') or '', c.get('paper_2') or '']
        out += [('' if r['progress']['delta'] is None else f"{r['progress']['delta']:g}%"), f"{r['progress']['label']} {r['progress'].get('milestone') or ''}".strip()]
        writer.writerow(out)
    resp=make_response(output.getvalue()); resp.headers['Content-Type']='text/csv'; resp.headers['Content-Disposition']=f'attachment; filename=class-year-overview-{ctx["subject"]}.csv'; return resp


@dashboards_bp.route('/class/year-overview')
@login_required
def class_year_overview():
    if not (current_user.is_teacher or current_user.can_manage_school):
        return redirect(url_for('dashboards.index'))
    ctx = _class_year_overview_context()
    fmt = (request.args.get('download') or '').lower()
    if fmt == 'csv':
        return _download_year_overview(ctx)
    if fmt == 'pdf':
        return _download_year_overview(ctx, as_pdf=True)
    if fmt == 'anon_pdf':
        return _download_year_overview(ctx, anonymised=True, as_pdf=True)
    return render_template('class_year_overview.html', **ctx)


@dashboards_bp.route('/admin/class-year-overview')
@login_required
@admin_required
def admin_class_year_overview():
    return class_year_overview()
