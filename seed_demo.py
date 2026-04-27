"""Safe demo-data seeding script (non-destructive, idempotent)."""

from __future__ import annotations

from app import create_app
from app.extensions import db
from app.models import Intervention, Pupil, SchoolClass, SubjectResult, User, WritingResult
from app.services import CORE_SUBJECTS, TERMS, compute_subject_result_values, get_current_academic_year, get_subject_setting

app = create_app()

DEMO_CLASSES = [(year, f'Demo Year {year}') for year in range(1, 7)]
DEMO_BANDS = ['WT', 'OT', 'EXS']


def ensure_demo_user(username: str, password: str, role: str) -> User:
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, role=role, is_active=True)
    user.role = role
    user.is_active = True
    user.require_password_change = False
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def ensure_demo_class(name: str, year_group: int, teacher_id: int | None = None) -> SchoolClass:
    school_class = SchoolClass.query.filter_by(name=name).first()
    if not school_class:
        school_class = SchoolClass(name=name, year_group=year_group)
    school_class.year_group = year_group
    school_class.teacher_id = teacher_id
    school_class.is_active = True
    db.session.add(school_class)
    db.session.flush()
    return school_class


def ensure_demo_pupil(school_class: SchoolClass, index: int) -> Pupil:
    first_name = 'Demo'
    last_name = f'Pupil {school_class.year_group}-{index}'
    pupil = Pupil.query.filter_by(first_name=first_name, last_name=last_name, class_id=school_class.id).first()
    if not pupil:
        pupil = Pupil(first_name=first_name, last_name=last_name, gender='Unknown', class_id=school_class.id)
    pupil.gender = 'Unknown'
    pupil.class_id = school_class.id
    pupil.is_active = True
    pupil.pupil_premium = index % 2 == 0
    pupil.laps = index % 3 == 0
    pupil.service_child = index % 4 == 0
    pupil.strengths_notes = 'DEMO FAKE DATA: Example strengths note for showcase use only.'
    pupil.next_steps_notes = 'DEMO FAKE DATA: Example next steps note for showcase use only.'
    pupil.general_notes = 'DEMO FAKE DATA: Not a real pupil profile.'
    db.session.add(pupil)
    db.session.flush()
    return pupil


def ensure_demo_assessments(pupil: Pupil, academic_year: str) -> None:
    term = 'spring'
    for subject in CORE_SUBJECTS:
        setting = get_subject_setting(pupil.school_class.year_group, subject, term)
        paper_1 = max(0, min(setting.paper_1_max, int(setting.paper_1_max * (0.35 + (pupil.id % 4) * 0.12))))
        paper_2 = max(0, min(setting.paper_2_max, int(setting.paper_2_max * (0.4 + (pupil.id % 3) * 0.15))))
        computed = compute_subject_result_values(setting, paper_1, paper_2)
        row = SubjectResult.query.filter_by(
            pupil_id=pupil.id,
            academic_year=academic_year,
            term=term,
            subject=subject,
        ).first()
        if not row:
            row = SubjectResult(pupil_id=pupil.id, academic_year=academic_year, term=term, subject=subject)
        row.paper_1_score = paper_1
        row.paper_2_score = paper_2
        row.combined_score = computed['combined_score']
        row.combined_percent = computed['combined_percent']
        row.band_label = computed['band_label']
        row.source = 'demo'
        row.notes = 'DEMO FAKE DATA: Example assessment result.'
        db.session.add(row)

    writing = WritingResult.query.filter_by(pupil_id=pupil.id, academic_year=academic_year, term=term).first()
    if not writing:
        writing = WritingResult(pupil_id=pupil.id, academic_year=academic_year, term=term, band='OT')
    writing.band = DEMO_BANDS[pupil.id % len(DEMO_BANDS)]
    writing.source = 'demo'
    writing.notes = 'DEMO FAKE DATA: Example writing judgement.'
    db.session.add(writing)


def ensure_demo_intervention(pupil: Pupil, academic_year: str) -> None:
    term = 'spring'
    subject = CORE_SUBJECTS[pupil.id % len(CORE_SUBJECTS)]
    row = Intervention.query.filter_by(pupil_id=pupil.id, subject=subject, term=term, academic_year=academic_year).first()
    if not row:
        row = Intervention(
            pupil_id=pupil.id,
            subject=subject,
            term=term,
            academic_year=academic_year,
            reason='DEMO FAKE DATA: Example intervention trigger.',
        )
    row.is_active = True
    row.auto_flagged = False
    row.note = 'DEMO FAKE DATA: Small group support example.'
    db.session.add(row)


def main() -> None:
    with app.app_context():
        db.create_all()

        demo_admin = ensure_demo_user('demo_admin', 'demo123', 'admin')
        demo_teacher = ensure_demo_user('demo_teacher', 'demo123', 'teacher')

        class_lookup: dict[int, SchoolClass] = {}
        for year_group, class_name in DEMO_CLASSES:
            teacher_id = demo_teacher.id if year_group == 1 else None
            class_lookup[year_group] = ensure_demo_class(class_name, year_group, teacher_id=teacher_id)

        academic_year = get_current_academic_year()
        for year_group in sorted(class_lookup):
            school_class = class_lookup[year_group]
            for index in range(1, 7):
                pupil = ensure_demo_pupil(school_class, index)
                ensure_demo_assessments(pupil, academic_year)
                if index <= 2:
                    ensure_demo_intervention(pupil, academic_year)

        db.session.commit()
        print('Demo seed completed safely.')
        print('Created/refreshed demo users: demo_admin, demo_teacher (password: demo123).')
        print('Demo classes Year 1 to Year 6 and fake pupils were created/updated without deleting existing data.')


if __name__ == '__main__':
    main()
