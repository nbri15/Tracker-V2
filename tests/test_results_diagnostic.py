"""Read-only saved results check page. Fictional data only."""
from app.extensions import db
from app.models import Pupil, SubjectResult
from test_assessment_reliability import login, world  # noqa: F401


def test_page_shows_results_by_class_and_status_and_flags_duplicate_names(world):  # noqa: F811
    app, ids = world
    with app.app_context():
        pupil = db.session.get(Pupil, ids['pupils'][0])
        copy = Pupil(first_name=pupil.first_name, last_name=pupil.last_name, gender='Female', school_id=ids['a'], is_active=False, is_archived=True)
        db.session.add(copy); db.session.flush()
        db.session.add_all([
            SubjectResult(pupil_id=pupil.id, school_id=ids['a'], academic_year='2025/26', term='spring', subject='maths', combined_percent=50),
            SubjectResult(pupil_id=copy.id, school_id=ids['a'], academic_year='2025/26', term='autumn', subject='maths', combined_percent=50)])
        db.session.commit()
    client = app.test_client(); login(client, ids['admin'])
    page = client.get('/admin/results-diagnostic')
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'Oak' in html and 'Active' in html          # spring result on the real pupil
    assert '(no class)' in html and 'Archived' in html  # autumn result on the copy
    assert 'Alice' in html.split('same name more than once')[1] and '<td>2</td>' in html


def test_page_is_admin_only_and_scoped_to_the_school(world):  # noqa: F811
    app, ids = world
    with app.app_context():
        db.session.add(SubjectResult(pupil_id=ids['other_pupil'], school_id=ids['b'], academic_year='2024/25', term='summer', subject='maths', combined_percent=40))
        db.session.commit()
    teacher = app.test_client(); login(teacher, ids['teacher'])
    assert teacher.get('/admin/results-diagnostic').status_code == 403
    admin = app.test_client(); login(admin, ids['admin'])
    assert '2024/25' not in admin.get('/admin/results-diagnostic').get_data(as_text=True)
