"""Admin routes for school setup and settings management."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import AssessmentSetting, Pupil, SchoolClass, User
from app.services import CORE_SUBJECTS, TERMS, format_subject_name, get_or_create_assessment_setting, get_setting_defaults, validate_setting_payload
from app.services.assessments import AssessmentValidationError
from app.utils import admin_required

from . import admin_bp
from .forms import AssessmentSettingForm


@admin_bp.route('/classes')
@login_required
@admin_required
def classes():
    """List available classes and their teacher assignments."""

    classes = SchoolClass.query.order_by(SchoolClass.year_group, SchoolClass.name).all()
    return render_template('admin/classes.html', classes=classes)


@admin_bp.route('/pupils')
@login_required
@admin_required
def pupils():
    """Display a basic pupil list."""

    pupils = Pupil.query.order_by(Pupil.last_name, Pupil.first_name).all()
    return render_template('admin/pupils.html', pupils=pupils)


def _parse_setting_form(prefix: str = '') -> dict:
    suffix = f'_{prefix}' if prefix else ''
    return {
        'year_group': int(request.form.get(f'year_group{suffix}', '0')),
        'subject': request.form.get(f'subject{suffix}', '').strip(),
        'term': request.form.get(f'term{suffix}', '').strip(),
        'paper_1_name': request.form.get(f'paper_1_name{suffix}', '').strip(),
        'paper_1_max': int(request.form.get(f'paper_1_max{suffix}', '0')),
        'paper_2_name': request.form.get(f'paper_2_name{suffix}', '').strip(),
        'paper_2_max': int(request.form.get(f'paper_2_max{suffix}', '0')),
        'combined_max': int(request.form.get(f'combined_max{suffix}', '0') or 0),
        'below_are_threshold_percent': float(request.form.get(f'below_are_threshold_percent{suffix}', '0') or 0),
        'on_track_threshold_percent': float(request.form.get(f'on_track_threshold_percent{suffix}', '0') or 0),
        'exceeding_threshold_percent': float(request.form.get(f'exceeding_threshold_percent{suffix}', '0') or 0),
    }


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """Display and manage assessment settings."""

    form = AssessmentSettingForm()
    filter_year_group = request.args.get('year_group', '').strip()
    filter_subject = request.args.get('subject', '').strip()
    filter_term = request.args.get('term', '').strip()

    if request.method == 'POST':
        action = request.form.get('action', 'create')
        try:
            if action == 'create':
                payload = validate_setting_payload(_parse_setting_form())
                setting = get_or_create_assessment_setting(payload['year_group'], payload['subject'], payload['term'])
                for field, value in payload.items():
                    setattr(setting, field, value)
                db.session.add(setting)
                db.session.commit()
                flash(
                    f"Saved {format_subject_name(setting.subject)} {setting.term.title()} settings for Year {setting.year_group}.",
                    'success',
                )
                return redirect(
                    url_for(
                        'admin.settings',
                        year_group=setting.year_group,
                        subject=setting.subject,
                        term=setting.term,
                    )
                )

            setting_id = int(request.form.get('setting_id', '0'))
            setting = AssessmentSetting.query.get_or_404(setting_id)
            payload = validate_setting_payload(_parse_setting_form(prefix=str(setting.id)))
            original_scope = (setting.year_group, setting.subject, setting.term)
            new_scope = (payload['year_group'], payload['subject'], payload['term'])
            existing = AssessmentSetting.query.filter_by(
                year_group=payload['year_group'],
                subject=payload['subject'],
                term=payload['term'],
            ).first()
            if existing and existing.id != setting.id and original_scope != new_scope:
                raise AssessmentValidationError('A setting already exists for that year group, subject, and term.')
            for field, value in payload.items():
                setattr(setting, field, value)
            db.session.commit()
            flash(
                f"Updated {format_subject_name(setting.subject)} {setting.term.title()} settings for Year {setting.year_group}.",
                'success',
            )
            return redirect(
                url_for(
                    'admin.settings',
                    year_group=payload['year_group'],
                    subject=payload['subject'],
                    term=payload['term'],
                )
            )
        except (ValueError, AssessmentValidationError) as exc:
            db.session.rollback()
            flash(f'Settings could not be saved: {exc}', 'danger')

    settings_query = AssessmentSetting.query
    if filter_year_group:
        settings_query = settings_query.filter(AssessmentSetting.year_group == int(filter_year_group))
    if filter_subject:
        settings_query = settings_query.filter(AssessmentSetting.subject == filter_subject)
    if filter_term:
        settings_query = settings_query.filter(AssessmentSetting.term == filter_term)

    settings = settings_query.order_by(
        AssessmentSetting.year_group,
        AssessmentSetting.subject,
        AssessmentSetting.term,
    ).all()

    if request.method == 'GET' and filter_year_group and filter_subject and filter_term:
        form.year_group.data = int(filter_year_group)
        form.subject.data = filter_subject
        form.term.data = filter_term
        setting = AssessmentSetting.query.filter_by(
            year_group=int(filter_year_group),
            subject=filter_subject,
            term=filter_term,
        ).first()
        if setting:
            form.paper_1_name.data = setting.paper_1_name
            form.paper_1_max.data = setting.paper_1_max
            form.paper_2_name.data = setting.paper_2_name
            form.paper_2_max.data = setting.paper_2_max
            form.combined_max.data = setting.combined_max
            form.below_are_threshold_percent.data = setting.below_are_threshold_percent
            form.on_track_threshold_percent.data = setting.on_track_threshold_percent
            form.exceeding_threshold_percent.data = setting.exceeding_threshold_percent
        elif filter_subject in CORE_SUBJECTS:
            defaults = get_setting_defaults(filter_subject)
            form.paper_1_name.data = defaults['paper_1_name']
            form.paper_1_max.data = defaults['paper_1_max']
            form.paper_2_name.data = defaults['paper_2_name']
            form.paper_2_max.data = defaults['paper_2_max']
            form.combined_max.data = defaults['combined_max']
            form.below_are_threshold_percent.data = defaults['below_are_threshold_percent']
            form.on_track_threshold_percent.data = defaults['on_track_threshold_percent']
            form.exceeding_threshold_percent.data = defaults['exceeding_threshold_percent']

    return render_template(
        'admin/settings.html',
        settings=settings,
        filter_year_group=filter_year_group,
        filter_subject=filter_subject,
        filter_term=filter_term,
        filter_subject_choices=[('', 'All subjects')] + [(subject, format_subject_name(subject)) for subject in CORE_SUBJECTS],
        filter_term_choices=[('', 'All terms')] + TERMS,
        form=form,
        terms=TERMS,
    )


@admin_bp.route('/imports')
@login_required
@admin_required
def imports():
    """Placeholder for future CSV import/export tooling."""

    overview = {
        'teachers': User.query.filter_by(role='teacher').count(),
        'classes': SchoolClass.query.count(),
        'pupils': Pupil.query.count(),
    }
    return render_template('admin/imports.html', overview=overview)
