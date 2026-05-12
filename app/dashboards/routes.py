"""Dashboard routing for role-aware landing pages."""

from datetime import datetime, timezone

from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Intervention, Pupil, SatsResult, SchoolClass, SimpleSatsExamTab, SimpleSatsSetting, User
from app.services import (
    BOOLEAN_FILTER_CHOICES,
    CLASS_SORT_OPTIONS,
    build_admin_pupil_filter_state,
    build_class_overview_row,
    build_dashboard_summary,
    build_subject_overview_cards,
    get_current_academic_year,
    get_gender_filter_options,
    get_tracker_mode,
    get_tracker_mode_label,
    sort_class_rows,
)
from app.utils import (
    admin_required,
    demo_filter_classes,
    demo_filter_pupils,
    get_primary_class_for_user,
    school_scoped_query,
    get_year_group_class_for_user,
    teacher_required,
)

from . import dashboards_bp


@dashboards_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboards.index'))
    return render_template('public_home.html')


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
    school_class = get_primary_class_for_user(current_user)
    pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all() if school_class else []
    academic_year = get_current_academic_year()
    summary_rows = build_dashboard_summary(school_class.id if school_class else None, academic_year)
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
        .order_by(Pupil.last_name, Pupil.first_name)
        .all()
        if school_class
        else []
    )

    context = {
        'school_class': school_class,
        'has_year6_sats_access': get_year_group_class_for_user(current_user, 6) is not None,
        'pupil_count': len(pupils),
        'academic_year': academic_year,
        'summary_rows': summary_rows,
        'chart_cards': summary_rows,
        'active_interventions': active_interventions,
        'tracker_mode': get_tracker_mode(school_class.year_group) if school_class else 'normal',
        'tracker_mode_label': get_tracker_mode_label(school_class.year_group) if school_class else 'Usual tracker',
    }
    return render_template('dashboards/teacher_dashboard.html', **context)


@dashboards_bp.route('/dashboard/admin')
@login_required
@admin_required
def admin_dashboard():
    academic_year = request.args.get('academic_year', get_current_academic_year())
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

    classes = query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    class_rows = [build_class_overview_row(school_class, academic_year, filters=pupil_filters) for school_class in classes]
    class_rows = sort_class_rows(class_rows, sort)
    subject_cards = build_subject_overview_cards(class_rows)
    teacher_options = school_scoped_query(User, User.query.filter_by(role='teacher', is_active=True, is_demo=current_user.is_demo)).order_by(User.username).all()
    class_options = demo_filter_classes(SchoolClass.query.filter_by(is_active=True)).order_by(SchoolClass.year_group, SchoolClass.name).all()
    year6_overview = {}

    context = {
        'academic_year': academic_year,
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


def _ensure_simple_tabs_and_settings(academic_year: str):
    tabs = SimpleSatsExamTab.query.filter_by(school_id=current_user.school_id, academic_year=academic_year).order_by(SimpleSatsExamTab.display_order).all()
    if not tabs:
        for n in range(1, 5):
            db.session.add(SimpleSatsExamTab(school_id=current_user.school_id, academic_year=academic_year, exam_number=n, name=f'Exam {n}', display_order=n, is_active=True))
            db.session.add(SimpleSatsSetting(school_id=current_user.school_id, academic_year=academic_year, exam_number=n))
        db.session.commit()
        tabs = SimpleSatsExamTab.query.filter_by(school_id=current_user.school_id, academic_year=academic_year).order_by(SimpleSatsExamTab.display_order).all()
    return tabs

@dashboards_bp.route('/sats/simple')
@login_required
def sats_simple():
    academic_year = request.args.get('academic_year', get_current_academic_year())
    exam_number = int((request.args.get('exam_number') or '1'))
    tabs = _ensure_simple_tabs_and_settings(academic_year)
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
                Pupil.school_id == current_user.school_id,
                Pupil.class_id == selected_class.id,
                Pupil.is_active.is_(True),
                SchoolClass.year_group == 6,
            )
            .order_by(Pupil.last_name, Pupil.first_name)
            .all()
        )
    pupil_ids=[p.id for p in pupils]
    result_map={}
    if pupil_ids:
        rows=SatsResult.query.filter(SatsResult.school_id==current_user.school_id,SatsResult.academic_year==academic_year,SatsResult.exam_number==exam_number,SatsResult.pupil_id.in_(pupil_ids)).all()
        result_map={r.pupil_id:r for r in rows}
    settings = {row.exam_number: row for row in SimpleSatsSetting.query.filter_by(school_id=current_user.school_id, academic_year=academic_year).all()}
    return render_template('sats_simple.html', academic_year=academic_year, exam_number=exam_number, pupils=pupils, result_map=result_map, class_options=class_options, selected_class=selected_class, settings=settings, tabs=tabs)

@dashboards_bp.route('/api/sats/simple/quick-save', methods=['POST'])
@login_required
def sats_simple_quick_save():
    data=request.get_json(silent=True) or request.form
    pupil_id=int(data.get('pupil_id'))
    exam_number=int(data.get('exam_number'))
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
            Pupil.school_id == current_user.school_id,
            SchoolClass.year_group == 6,
        )
        .first()
    )
    if not pupil or pupil.school_id!=current_user.school_id:
        return {'ok':False,'error':'Forbidden'},403
    academic_year=str(data.get('academic_year') or get_current_academic_year())
    rec=SatsResult.query.filter_by(school_id=current_user.school_id,pupil_id=pupil_id,academic_year=academic_year,exam_number=exam_number).first()
    if not rec:
        rec=SatsResult(school_id=current_user.school_id,pupil_id=pupil_id,academic_year=academic_year,exam_number=exam_number,subject='maths',assessment_point=exam_number,is_most_recent=False)
        db.session.add(rec)
    setattr(rec, field, value_raw.strip() if field == 'notes' and str(value_raw).strip() != '' else (int(value_raw) if str(value_raw).strip()!='' else None))
    a,b,c=rec.arithmetic_score or 0, rec.reasoning_1_score or 0, rec.reasoning_2_score or 0
    s,g=rec.spelling_score or 0, rec.grammar_score or 0
    rec.maths_combined_score=a+b+c
    rec.spag_combined_score=s+g
    db.session.commit()
    return {'ok':True,'maths_combined_score':rec.maths_combined_score,'spag_combined_score':rec.spag_combined_score}


@dashboards_bp.route('/api/sats/simple/add-exam', methods=['POST'])
@login_required
def sats_simple_add_exam():
    academic_year = str((request.get_json(silent=True) or {}).get('academic_year') or get_current_academic_year())
    tabs = _ensure_simple_tabs_and_settings(academic_year)
    next_exam = max([tab.exam_number for tab in tabs], default=0) + 1
    db.session.add(SimpleSatsExamTab(school_id=current_user.school_id, academic_year=academic_year, exam_number=next_exam, name=f'Exam {next_exam}', display_order=next_exam, is_active=True))
    db.session.add(SimpleSatsSetting(school_id=current_user.school_id, academic_year=academic_year, exam_number=next_exam))
    db.session.commit()
    return {'ok': True, 'exam_number': next_exam}


@dashboards_bp.route('/api/sats/simple/settings', methods=['POST'])
@login_required
def sats_simple_save_settings():
    data = request.get_json(silent=True) or request.form
    academic_year = str(data.get('academic_year') or get_current_academic_year())
    exam_number = int(data.get('exam_number'))
    settings = SimpleSatsSetting.query.filter_by(school_id=current_user.school_id, academic_year=academic_year, exam_number=exam_number).first()
    if not settings:
        settings = SimpleSatsSetting(school_id=current_user.school_id, academic_year=academic_year, exam_number=exam_number)
    for field in ['arithmetic_max', 'reasoning_1_max', 'reasoning_2_max', 'reading_max', 'spelling_max', 'grammar_max']:
        setattr(settings, field, int(data.get(field) or getattr(settings, field)))
    settings.updated_at = datetime.now(timezone.utc)
    db.session.add(settings)
    db.session.commit()
    return {'ok': True}
