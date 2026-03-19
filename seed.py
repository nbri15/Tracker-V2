"""Development seed script for initial local data."""

from app import create_app
from app.extensions import db
from app.models import AssessmentSetting, Pupil, SchoolClass, User


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
    for first_name, last_name, gender, pupil_premium, laps, service_child, class_name in pupil_specs:
        pupil = Pupil.query.filter_by(first_name=first_name, last_name=last_name).first()
        if not pupil:
            db.session.add(
                Pupil(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    pupil_premium=pupil_premium,
                    laps=laps,
                    service_child=service_child,
                    class_id=class_lookup[class_name].id,
                )
            )

    setting_specs = [
        (3, 'maths', 'autumn', 'Arithmetic', 40, 'Reasoning', 35, 75, 39.0, 60.0, 80.0),
        (3, 'reading', 'autumn', 'Paper 1', 30, 'Paper 2', 20, 50, 39.0, 60.0, 80.0),
        (6, 'spag', 'spring', 'SPaG Test', 50, 'Teacher Check', 10, 60, 40.0, 62.0, 82.0),
    ]
    for spec in setting_specs:
        scope = {'year_group': spec[0], 'subject': spec[1], 'term': spec[2]}
        setting = AssessmentSetting.query.filter_by(**scope).first()
        if not setting:
            db.session.add(
                AssessmentSetting(
                    year_group=spec[0],
                    subject=spec[1],
                    term=spec[2],
                    paper_1_name=spec[3],
                    paper_1_max=spec[4],
                    paper_2_name=spec[5],
                    paper_2_max=spec[6],
                    combined_max=spec[7],
                    below_are_threshold_percent=spec[8],
                    on_track_threshold_percent=spec[9],
                    exceeding_threshold_percent=spec[10],
                )
            )

    db.session.commit()
    print('Seed data created or updated successfully.')
