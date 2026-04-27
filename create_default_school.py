"""Safe idempotent backfill for multi-school tenancy."""

from app import create_app
from app.extensions import db
from app.models import (
    AcademicYear,
    AssessmentSetting,
    FoundationResult,
    GapQuestion,
    GapScore,
    GapTemplate,
    Intervention,
    PhonicsScore,
    PhonicsTestColumn,
    Pupil,
    PupilClassHistory,
    ReceptionTrackerEntry,
    SatsColumnResult,
    SatsColumnSetting,
    SatsExamTab,
    SatsResult,
    SatsWritingResult,
    School,
    SchoolClass,
    SubjectResult,
    TimesTableScore,
    TimesTableTestColumn,
    TrackerModeSetting,
    User,
    WritingResult,
)


def _ensure_school(name: str, slug: str, *, is_demo: bool) -> School:
    school = School.query.filter_by(slug=slug).first()
    if not school:
        school = School(name=name, slug=slug, is_demo=is_demo, is_active=True)
        db.session.add(school)
        db.session.flush()
    return school


def _backfill(model, *, demo_field: str | None = None, demo_school_id: int, default_school_id: int) -> int:
    updated = 0
    rows = model.query.filter(model.school_id.is_(None)).all()
    for row in rows:
        if demo_field and getattr(row, demo_field, False):
            row.school_id = demo_school_id
        else:
            row.school_id = default_school_id
        db.session.add(row)
        updated += 1
    return updated


def run_backfill() -> dict[str, int]:
    barrow = _ensure_school('Barrow School', 'barrow-school', is_demo=False)
    demo = _ensure_school('Demo School', 'demo-school', is_demo=True)

    counts = {}
    counts['users'] = _backfill(User, demo_field='is_demo', demo_school_id=demo.id, default_school_id=barrow.id)
    counts['school_classes'] = _backfill(SchoolClass, demo_field='is_demo', demo_school_id=demo.id, default_school_id=barrow.id)
    counts['pupils'] = _backfill(Pupil, demo_field='is_demo', demo_school_id=demo.id, default_school_id=barrow.id)
    counts['interventions'] = _backfill(Intervention, demo_field='is_demo', demo_school_id=demo.id, default_school_id=barrow.id)

    for model_name, model in {
        'academic_years': AcademicYear,
        'assessment_settings': AssessmentSetting,
        'subject_results': SubjectResult,
        'writing_results': WritingResult,
        'gap_templates': GapTemplate,
        'gap_questions': GapQuestion,
        'gap_scores': GapScore,
        'reception_tracker_entries': ReceptionTrackerEntry,
        'phonics_test_columns': PhonicsTestColumn,
        'phonics_scores': PhonicsScore,
        'times_table_test_columns': TimesTableTestColumn,
        'times_table_scores': TimesTableScore,
        'foundation_results': FoundationResult,
        'tracker_mode_settings': TrackerModeSetting,
        'sats_exam_tabs': SatsExamTab,
        'sats_column_settings': SatsColumnSetting,
        'sats_column_results': SatsColumnResult,
        'sats_results': SatsResult,
        'sats_writing_results': SatsWritingResult,
        'pupil_class_history': PupilClassHistory,
    }.items():
        counts[model_name] = _backfill(model, demo_school_id=demo.id, default_school_id=barrow.id)

    User.query.filter(User.role == 'admin').update({'role': 'school_admin'})
    db.session.commit()
    return counts


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        results = run_backfill()
        print('Backfill complete:', results)
