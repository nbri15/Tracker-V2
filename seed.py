"""Development seed script for local assessment tracker data."""

from app import create_app
from app.extensions import db
from app.models import AssessmentSetting, Pupil, SchoolClass, SubjectResult, User, WritingResult
from app.services import CORE_SUBJECTS, TERMS, WRITING_BAND_CHOICES, compute_subject_result_values, get_current_academic_year, get_or_create_assessment_setting


app = create_app()


with app.app_context():
    db.create_all()

    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', role='admin')
        admin.set_password('admin1234')
        db.session.add(admin)

    teacher = User.query.filter_by(username='teacher1').first()
    if not teacher:
        teacher = User(username='teacher1', role='teacher')
        teacher.set_password('teacher1234')
        db.session.add(teacher)

    db.session.flush()

    class_specs = [
        ('Year 3', 3, teacher.id),
        ('Year 6', 6, None),
    ]
    class_lookup = {}
    for name, year_group, teacher_id in class_specs:
        school_class = SchoolClass.query.filter_by(name=name).first()
        if not school_class:
            school_class = SchoolClass(name=name, year_group=year_group, teacher_id=teacher_id)
            db.session.add(school_class)
        elif teacher_id and school_class.teacher_id is None:
            school_class.teacher_id = teacher_id
        class_lookup[name] = school_class

    db.session.flush()

    pupil_specs = [
        ('Ava', 'Brown', 'Female', False, False, False, 'Year 3'),
        ('Ethan', 'Wilson', 'Male', True, False, False, 'Year 3'),
        ('Mia', 'Taylor', 'Female', False, True, False, 'Year 3'),
        ('Noah', 'Hughes', 'Male', False, False, True, 'Year 3'),
        ('Grace', 'Patel', 'Female', True, False, False, 'Year 3'),
        ('Leo', 'Evans', 'Male', False, False, False, 'Year 6'),
        ('Sophie', 'Johnson', 'Female', True, False, False, 'Year 6'),
        ('Oliver', 'Clarke', 'Male', False, True, False, 'Year 6'),
        ('Isla', 'Roberts', 'Female', False, False, True, 'Year 6'),
        ('Jack', 'Davies', 'Male', True, False, False, 'Year 6'),
    ]
    pupil_lookup = {}
    for first_name, last_name, gender, pupil_premium, laps, service_child, class_name in pupil_specs:
        pupil = Pupil.query.filter_by(first_name=first_name, last_name=last_name).first()
        if not pupil:
            pupil = Pupil(
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                pupil_premium=pupil_premium,
                laps=laps,
                service_child=service_child,
                class_id=class_lookup[class_name].id,
            )
            db.session.add(pupil)
        pupil_lookup[f'{first_name} {last_name}'] = pupil

    db.session.flush()

    for year_group in range(1, 7):
        for subject in CORE_SUBJECTS:
            for term, _ in TERMS:
                get_or_create_assessment_setting(year_group, subject, term)

    db.session.flush()

    academic_year = get_current_academic_year()
    teacher_pupils = (
        Pupil.query.filter_by(class_id=class_lookup['Year 3'].id, is_active=True)
        .order_by(Pupil.last_name, Pupil.first_name)
        .all()
    )

    sample_subject_scores = {
        'maths': [(28, 22), (31, 25), (16, 14), (24, 18), (34, 30)],
        'reading': [(18, 15), (23, 17), (12, 10), (19, 13), (24, 18)],
        'spag': [(14, 22), (18, 25), (10, 14), (13, 18), (19, 28)],
    }
    sample_terms = {'maths': 'spring', 'reading': 'spring', 'spag': 'spring'}

    for subject, rows in sample_subject_scores.items():
        setting = AssessmentSetting.query.filter_by(year_group=3, subject=subject, term=sample_terms[subject]).first()
        for pupil, (paper_1_score, paper_2_score) in zip(teacher_pupils, rows, strict=False):
            computed = compute_subject_result_values(setting, paper_1_score, paper_2_score)
            result = SubjectResult.query.filter_by(
                pupil_id=pupil.id,
                academic_year=academic_year,
                term=sample_terms[subject],
                subject=subject,
            ).first()
            if not result:
                result = SubjectResult(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    term=sample_terms[subject],
                    subject=subject,
                )
            result.paper_1_score = paper_1_score
            result.paper_2_score = paper_2_score
            result.combined_score = computed['combined_score']
            result.combined_percent = computed['combined_percent']
            result.band_label = computed['band_label']
            result.source = 'manual'
            result.notes = f'Seeded sample {subject} result'
            db.session.add(result)

    writing_bands = ['expected', 'greater_depth', 'working_towards', 'expected', 'greater_depth']
    for pupil, band in zip(teacher_pupils, writing_bands, strict=False):
        result = WritingResult.query.filter_by(
            pupil_id=pupil.id,
            academic_year=academic_year,
            term='spring',
        ).first()
        if not result:
            result = WritingResult(pupil_id=pupil.id, academic_year=academic_year, term='spring', band=band)
        result.band = band
        result.notes = 'Seeded sample writing judgement'
        db.session.add(result)

    db.session.commit()
    print('Seed data created or updated successfully.')
