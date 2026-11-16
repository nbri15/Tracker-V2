"""Teachers can add programmes and change maximum marks for their own year group. Fictional data only."""
from app.extensions import db
from app.models import AssessmentConfiguration, AssessmentReview, AuditLog, InterventionProgramme
from test_assessment_reliability import login, world  # noqa: F401  (world is a pytest fixture)
from test_intervention_programmes import library  # noqa: F401  (pytest fixture)

SETUP = {'academic_year': '2026/27', 'subject': 'maths', 'term': 'autumn'}


# ---- programmes ---------------------------------------------------------------------------

def test_teacher_can_create_a_programme_for_their_school(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['teacher'])
    response = client.post('/teacher/intervention-programmes', data={'action': 'save', 'name': 'Times tables club', 'subject': 'maths', 'description': 'Ten minutes daily'})
    assert response.status_code == 302
    with app.app_context():
        programme = InterventionProgramme.query.filter_by(name='Times tables club').one()
        assert programme.school_id == ids['a'] and programme.is_active
        assert AuditLog.query.filter_by(action='intervention_programme_created').count() == 1


def test_teacher_programme_names_must_be_unique_and_valid(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['teacher'])
    client.post('/teacher/intervention-programmes', data={'action': 'save', 'name': ' MATHS BOOSTER ', 'subject': 'maths'})
    client.post('/teacher/intervention-programmes', data={'action': 'save', 'name': '', 'subject': 'maths'})
    client.post('/teacher/intervention-programmes', data={'action': 'save', 'name': 'Science club', 'subject': 'science'})
    with app.app_context():
        assert InterventionProgramme.query.filter_by(school_id=ids['a'], subject='maths').count() == 2
        assert InterventionProgramme.query.filter_by(name='Science club').count() == 0


def test_teacher_cannot_touch_another_schools_programme(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['teacher'])
    response = client.post('/teacher/intervention-programmes', data={'action': 'toggle', 'programme_id': ids['foreign_programme']})
    assert response.status_code == 404
    response = client.post('/teacher/intervention-programmes', data={'action': 'save', 'programme_id': ids['foreign_programme'], 'name': 'Hijacked', 'subject': 'maths'})
    assert response.status_code == 404
    with app.app_context():
        programme = db.session.get(InterventionProgramme, ids['foreign_programme'])
        assert programme.name == 'Private booster' and programme.is_active


def test_teacher_can_archive_and_restore_and_page_hides_other_schools(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['teacher'])
    page = client.get('/teacher/intervention-programmes')
    assert page.status_code == 200 and b'Maths booster' in page.data and b'Private booster' not in page.data
    client.post('/teacher/intervention-programmes', data={'action': 'toggle', 'programme_id': ids['programme']})
    with app.app_context():
        assert not db.session.get(InterventionProgramme, ids['programme']).is_active
    client.post('/teacher/intervention-programmes', data={'action': 'toggle', 'programme_id': ids['programme']})
    with app.app_context():
        assert db.session.get(InterventionProgramme, ids['programme']).is_active


def test_programme_page_is_for_teachers_only(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['admin'])
    assert client.get('/teacher/intervention-programmes').status_code == 403


def test_admin_programme_editing_still_works_after_sharing_the_save_logic(library):  # noqa: F811
    app, ids = library
    client = app.test_client(); login(client, ids['admin'])
    client.post('/admin/intervention-programmes', data={'action': 'save', 'name': 'Phonics catch-up', 'subject': 'reading'})
    client.post('/admin/intervention-programmes', data={'action': 'save', 'name': 'phonics CATCH-UP', 'subject': 'reading'})
    with app.app_context():
        assert InterventionProgramme.query.filter_by(name_key='phonics catch-up').count() == 1


# ---- maximum marks ------------------------------------------------------------------------

def test_teacher_sees_the_max_marks_page(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    page = client.get('/teacher/assessments/setup', query_string=SETUP)
    assert page.status_code == 200 and b'every Year 5 pupil' in page.data


def test_max_marks_page_is_for_teachers_only(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['admin'])
    assert client.get('/teacher/assessments/setup', query_string=SETUP).status_code == 403


def test_teacher_changes_max_marks_after_a_preview_and_thresholds_stay(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    response = client.post('/teacher/assessments/setup', data={**SETUP, 'paper_1_max': '50', 'paper_2_max': '35'})
    assert response.status_code == 302 and '/assessments/review/' in response.location
    with app.app_context():
        assert AssessmentConfiguration.query.count() == 0, 'Nothing is saved until the preview is confirmed'
    page = client.get(response.location)
    assert page.status_code == 200 and b'Nothing has been applied' in page.data
    confirmed = client.post(response.location, data={'action': 'apply'}, follow_redirects=True)
    assert confirmed.status_code == 200 and b'recalculated for 2026/27 only' in confirmed.data
    with app.app_context():
        saved = AssessmentConfiguration.query.filter_by(school_id=ids['a'], year_group=5, subject='maths', term='autumn', academic_year='2026/27').one()
        assert saved.paper_1_max == 50 and saved.paper_2_max == 35 and saved.combined_max == 85
        from app.services.assessments import get_subject_setting
        defaults = get_subject_setting(5, 'maths', 'summer', '2026/27', school_id=ids['a'])
        assert saved.below_are_threshold_percent == defaults.below_are_threshold_percent
        assert saved.exceeding_threshold_percent == defaults.exceeding_threshold_percent


def test_teacher_cannot_choose_another_year_group_or_school(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    response = client.post('/teacher/assessments/setup', data={**SETUP, 'year_group': '3', 'school_id': ids['b'], 'paper_1_max': '45', 'paper_2_max': '35'})
    assert response.status_code == 302
    with app.app_context():
        review = AssessmentReview.query.one()
        assert review.payload['year_group'] == 5 and review.school_id == ids['a']
        assert review.payload['teacher_request'] is True and review.payload['class_id'] == ids['ca']


def test_unchanged_or_invalid_max_marks_are_rejected(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    for data in ({'paper_1_max': '40', 'paper_2_max': '35'}, {'paper_1_max': '0', 'paper_2_max': '35'},
                 {'paper_1_max': 'abc', 'paper_2_max': '35'}, {'paper_1_max': '', 'paper_2_max': ''}):
        response = client.post('/teacher/assessments/setup', data={**SETUP, **data})
        assert response.status_code == 200, data
    with app.app_context():
        assert AssessmentReview.query.count() == 0


def test_other_users_cannot_open_or_apply_a_teachers_review(world):  # noqa: F811
    app, ids = world
    teacher = app.test_client(); login(teacher, ids['teacher'])
    response = teacher.post('/teacher/assessments/setup', data={**SETUP, 'paper_1_max': '50', 'paper_2_max': '35'})
    for user in (ids['admin'], ids['other']):
        client = app.test_client(); login(client, user)
        assert client.get(response.location).status_code in {403, 404}
        assert client.post(response.location, data={'action': 'apply'}).status_code in {403, 404}
    with app.app_context():
        assert AssessmentConfiguration.query.count() == 0
