"""Development seed script for local assessment tracker data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from app import create_app
from app.extensions import db
from app.models import (
    AssessmentSetting,
    GapQuestion,
    GapScore,
    GapTemplate,
    Intervention,
    Pupil,
    SatsResult,
    SatsWritingResult,
    SchoolClass,
    SubjectResult,
    User,
    WritingResult,
)
from app.services import (
    CORE_SUBJECTS,
    SATS_ASSESSMENT_POINTS,
    SATS_SUBJECTS,
    TERMS,
    WRITING_BAND_CHOICES,
    compute_subject_result_values,
    get_current_academic_year,
    get_or_create_assessment_setting,
    get_subject_setting,
)


app = create_app()


@dataclass(frozen=True)
class DefaultLogin:
    username: str
    password: str
    role: str
    class_name: str | None = None
    year_group: int | None = None


DEFAULT_ADMIN = DefaultLogin(username='admin', password='admin123', role='admin')
DEFAULT_TEACHERS = [
    DefaultLogin(
        username=f'teacher{year_group}',
        password=f'teacher{year_group}',
        role='teacher',
        class_name=f'Year {year_group}',
        year_group=year_group,
    )
    for year_group in range(1, 7)
]
DEFAULT_CLASSES = [
    {'name': f'Year {year_group}', 'year_group': year_group}
    for year_group in range(1, 7)
]

PUPIL_SPECS = {
    'Year 1': [('Ava', 'Brown', 'Female', False, False, False), ('Theo', 'Mills', 'Male', True, False, False), ('Elsie', 'Hall', 'Female', False, True, False), ('Adam', 'Young', 'Male', False, False, True)],
    'Year 2': [('Ruby', 'King', 'Female', True, False, False), ('Hugo', 'Baker', 'Male', False, False, False), ('Lily', 'Green', 'Female', False, True, False), ('Arlo', 'Bell', 'Male', False, False, True)],
    'Year 3': [('Ethan', 'Wilson', 'Male', True, False, False), ('Mia', 'Taylor', 'Female', False, True, False), ('Noah', 'Hughes', 'Male', False, False, True), ('Grace', 'Patel', 'Female', True, False, False)],
    'Year 4': [('Lucas', 'Scott', 'Male', False, False, False), ('Evie', 'Turner', 'Female', True, False, False), ('Zara', 'Cook', 'Female', False, True, False), ('Jacob', 'Ward', 'Male', False, False, True)],
    'Year 5': [('Amelia', 'Price', 'Female', True, False, False), ('Mason', 'Gray', 'Male', False, False, False), ('Isla', 'Carter', 'Female', False, True, False), ('Oscar', 'Reed', 'Male', False, False, True)],
    'Year 6': [('Leo', 'Evans', 'Male', False, False, False), ('Sophie', 'Johnson', 'Female', True, False, False), ('Oliver', 'Clarke', 'Male', False, True, False), ('Isla', 'Roberts', 'Female', False, False, True), ('Jack', 'Davies', 'Male', True, False, False), ('Maya', 'Shaw', 'Female', False, False, False)],
}

RESET_DELETE_ORDER = [
    GapScore,
    GapQuestion,
    GapTemplate,
    SatsWritingResult,
    SatsResult,
    WritingResult,
    SubjectResult,
    Intervention,
    Pupil,
    SchoolClass,
    AssessmentSetting,
    User,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Seed development data for Tracker-V2.')
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Delete existing development data before recreating the default classes, users, and samples.',
    )
    return parser.parse_args()


def clear_existing_dev_data() -> None:
    """Remove existing dev data so the seed can rebuild from a clean slate."""

    for model in RESET_DELETE_ORDER:
        db.session.query(model).delete()
    db.session.commit()


def upsert_user(login: DefaultLogin) -> User:
    """Create or update a default login and reset its password/role."""

    user = User.query.filter_by(username=login.username).first()
    if not user:
        user = User(username=login.username)
    user.username = login.username
    user.role = login.role
    user.is_active = True
    user.set_password(login.password)
    db.session.add(user)
    db.session.flush()
    return user


def upsert_class(name: str, year_group: int, teacher: User | None = None) -> SchoolClass:
    """Create or update a class and assign the expected teacher."""

    school_class = SchoolClass.query.filter_by(name=name).first()
    if not school_class:
        school_class = SchoolClass(name=name, year_group=year_group)
    school_class.name = name
    school_class.year_group = year_group
    school_class.teacher_id = teacher.id if teacher else None
    school_class.is_active = True
    db.session.add(school_class)
    db.session.flush()
    return school_class


def ensure_default_classes_and_teachers() -> tuple[User, dict[int, User], dict[str, SchoolClass]]:
    """Upsert the documented admin and teacher logins plus Year 1-6 classes."""

    admin = upsert_user(DEFAULT_ADMIN)
    teachers = {login.year_group: upsert_user(login) for login in DEFAULT_TEACHERS}

    class_lookup: dict[str, SchoolClass] = {}
    for class_spec in DEFAULT_CLASSES:
        year_group = class_spec['year_group']
        school_class = upsert_class(class_spec['name'], year_group, teachers[year_group])
        class_lookup[school_class.name] = school_class

    db.session.flush()
    return admin, teachers, class_lookup


def upsert_pupil(
    first_name: str,
    last_name: str,
    gender: str,
    pupil_premium: bool,
    laps: bool,
    service_child: bool,
    school_class: SchoolClass,
) -> Pupil:
    """Create or update a seeded pupil in the expected class."""

    pupil = Pupil.query.filter_by(first_name=first_name, last_name=last_name, class_id=school_class.id).first()
    if not pupil:
        pupil = Pupil(first_name=first_name, last_name=last_name, gender=gender, class_id=school_class.id)
    pupil.gender = gender
    pupil.pupil_premium = pupil_premium
    pupil.laps = laps
    pupil.service_child = service_child
    pupil.class_id = school_class.id
    pupil.is_active = True
    db.session.add(pupil)
    db.session.flush()
    return pupil


def seed_pupils(class_lookup: dict[str, SchoolClass]) -> dict[str, Pupil]:
    """Ensure the sample pupils exist for each seeded class."""

    pupil_lookup: dict[str, Pupil] = {}
    for class_name, rows in PUPIL_SPECS.items():
        for row in rows:
            pupil = upsert_pupil(*row, school_class=class_lookup[class_name])
            pupil_lookup[pupil.full_name] = pupil
    return pupil_lookup


def seed_assessment_settings() -> None:
    """Ensure editable subject settings exist for each year group and term."""

    for year_group in range(1, 7):
        for subject in CORE_SUBJECTS:
            for term, _ in TERMS:
                get_or_create_assessment_setting(year_group, subject, term)


def seed_subject_and_writing_results(class_lookup: dict[str, SchoolClass], academic_year: str) -> None:
    """Ensure the sample subject and writing rows exist for local development."""

    for school_class in class_lookup.values():
        pupils = school_class.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
        sample_term = 'spring' if school_class.year_group < 6 else 'autumn'
        for subject in CORE_SUBJECTS:
            setting = get_subject_setting(school_class.year_group, subject, sample_term)
            for index, pupil in enumerate(pupils, start=1):
                paper_1_score = min(setting.paper_1_max, max(0, int(setting.paper_1_max * (0.35 + (index * 0.08)))))
                paper_2_score = min(setting.paper_2_max, max(0, int(setting.paper_2_max * (0.3 + (index * 0.1)))))
                computed = compute_subject_result_values(setting, paper_1_score, paper_2_score)
                result = SubjectResult.query.filter_by(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    term=sample_term,
                    subject=subject,
                ).first()
                if not result:
                    result = SubjectResult(
                        pupil_id=pupil.id,
                        academic_year=academic_year,
                        term=sample_term,
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

        writing_cycle = [choice[0] for choice in WRITING_BAND_CHOICES]
        for index, pupil in enumerate(pupils):
            result = WritingResult.query.filter_by(
                pupil_id=pupil.id,
                academic_year=academic_year,
                term=sample_term,
            ).first()
            if not result:
                result = WritingResult(
                    pupil_id=pupil.id,
                    academic_year=academic_year,
                    term=sample_term,
                    band=writing_cycle[index % len(writing_cycle)],
                )
            result.band = writing_cycle[index % len(writing_cycle)]
            result.notes = 'Seeded sample writing judgement'
            db.session.add(result)


def seed_gap_and_intervention_data(class_lookup: dict[str, SchoolClass], academic_year: str) -> None:
    """Ensure the existing GAP and intervention sample data remains available."""

    year6 = class_lookup['Year 6']
    for subject in CORE_SUBJECTS:
        template = GapTemplate.query.filter_by(
            year_group=6,
            subject=subject,
            term='autumn',
            academic_year=academic_year,
        ).first()
        if not template:
            template = GapTemplate(
                year_group=6,
                subject=subject,
                term='autumn',
                academic_year=academic_year,
                paper_name=f'{subject.title()} Autumn paper',
            )
            db.session.add(template)
            db.session.flush()

        question_labels = ['1', '2', '3a', '3b', '4']
        questions: list[GapQuestion] = []
        for order, label in enumerate(question_labels, start=1):
            question = GapQuestion.query.filter_by(template_id=template.id, question_label=label).first()
            if not question:
                question = GapQuestion(template_id=template.id, question_label=label)
            question.question_type = ['Number', 'Reasoning', 'Retrieval', 'Inference', 'Proof'][order - 1]
            question.max_score = 4
            question.display_order = order
            db.session.add(question)
            questions.append(question)
        db.session.flush()

        for pupil_index, pupil in enumerate(
            year6.pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all(),
            start=1,
        ):
            for question_index, question in enumerate(questions, start=1):
                score_value = min(question.max_score, max(0, (pupil_index + question_index) % 5))
                score = GapScore.query.filter_by(pupil_id=pupil.id, question_id=question.id).first()
                if not score:
                    score = GapScore(pupil_id=pupil.id, question_id=question.id)
                score.score = score_value
                db.session.add(score)

    year3_pupils = class_lookup['Year 3'].pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all()
    for pupil in year3_pupils[:3]:
        intervention = Intervention.query.filter_by(
            pupil_id=pupil.id,
            subject='maths',
            term='spring',
            academic_year=academic_year,
        ).first()
        if not intervention:
            intervention = Intervention(
                pupil_id=pupil.id,
                subject='maths',
                term='spring',
                academic_year=academic_year,
                reason='Closest pupils below pass threshold',
                auto_flagged=True,
            )
        intervention.is_active = True
        intervention.note = 'Seeded follow-up group.'
        db.session.add(intervention)


def seed_sats_data(class_lookup: dict[str, SchoolClass], academic_year: str) -> None:
    """Ensure Year 6 SATs sample data exists."""

    for pupil_index, pupil in enumerate(
        class_lookup['Year 6'].pupils.filter_by(is_active=True).order_by(Pupil.last_name, Pupil.first_name).all(),
        start=1,
    ):
        for subject in SATS_SUBJECTS:
            for point in SATS_ASSESSMENT_POINTS:
                row = SatsResult.query.filter_by(
                    pupil_id=pupil.id,
                    subject=subject,
                    assessment_point=point,
                    academic_year=academic_year,
                ).first()
                if not row:
                    row = SatsResult(
                        pupil_id=pupil.id,
                        subject=subject,
                        assessment_point=point,
                        academic_year=academic_year,
                    )
                row.raw_score = 18 + pupil_index + point
                row.scaled_score = 96 + pupil_index + (point * 2)
                row.is_most_recent = point == max(SATS_ASSESSMENT_POINTS)
                db.session.add(row)

        for point in SATS_ASSESSMENT_POINTS:
            row = SatsWritingResult.query.filter_by(
                pupil_id=pupil.id,
                assessment_point=point,
                academic_year=academic_year,
            ).first()
            if not row:
                row = SatsWritingResult(
                    pupil_id=pupil.id,
                    assessment_point=point,
                    academic_year=academic_year,
                )
            row.band = WRITING_BAND_CHOICES[(pupil_index + point) % len(WRITING_BAND_CHOICES)][0]
            row.notes = f'Seeded writing point {point}'
            db.session.add(row)


def print_seed_summary(reset_requested: bool) -> None:
    """Print the documented dev logins and class links for quick reference."""

    mode_label = 'hard reset + seed' if reset_requested else 'seed refresh'
    print(f'Development {mode_label} completed successfully.')
    print('Default development logins:')
    print(f'  {DEFAULT_ADMIN.username} -> {DEFAULT_ADMIN.password}')
    for login in DEFAULT_TEACHERS:
        print(f'  {login.username} -> {login.class_name} ({login.password})')
    if reset_requested:
        print('Reset mode deleted existing development data before recreating the defaults.')


def main() -> None:
    args = parse_args()

    with app.app_context():
        db.create_all()

        if args.reset:
            clear_existing_dev_data()

        _, _, class_lookup = ensure_default_classes_and_teachers()
        seed_pupils(class_lookup)
        seed_assessment_settings()

        academic_year = get_current_academic_year()
        seed_subject_and_writing_results(class_lookup, academic_year)
        seed_gap_and_intervention_data(class_lookup, academic_year)
        seed_sats_data(class_lookup, academic_year)

        db.session.commit()
        print_seed_summary(args.reset)


if __name__ == '__main__':
    main()
