"""School programme management and teacher assignment use fictional, disposable data."""
import csv
import io
import pytest
from flask_login import login_user
from app.extensions import db
from app.models import (Intervention, InterventionProgramme, InterventionProgrammeAssignment,
                        Pupil, SchoolClass, SubjectResult, User)
from app.services.interventions import sync_auto_interventions, get_current_score_for_intervention, intervention_assessment
from test_assessment_reliability import world, login


SCOPE = {'academic_year': '2026/27', 'term': 'autumn', 'subject': 'maths'}


@pytest.fixture
def library(world):
    app, ids = world
    with app.app_context():
        programmes = [InterventionProgramme(school_id=school, name=name, name_key=name.casefold(), subject=subject)
                      for school, name, subject in [(ids['a'], 'Maths booster', 'maths'),
                          (ids['a'], 'Number confidence', 'maths'), (ids['b'], 'Private booster', 'maths'),
                          (ids['a'], 'Reading group', 'reading')]]
        record = Intervention(school_id=ids['a'], pupil_id=ids['pupils'][0], subject='maths', term='autumn',
            academic_year='2026/27', reason='Closest pupils below pass threshold', note='Keep existing plan', auto_flagged=True, is_active=True)
        other_class = SchoolClass(school_id=ids['a'], name='Birch', year_group=5, is_active=True)
        other_pupil = Pupil(school_id=ids['a'], school_class=other_class, first_name='Birch', last_name='Fictional', gender='Male', is_active=True)
        db.session.add_all([*programmes, record, other_class, other_pupil]); db.session.commit()
        ids.update(programme=programmes[0].id, second_programme=programmes[1].id,
                   foreign_programme=programmes[2].id, reading_programme=programmes[3].id,
                   record=record.id, same_school_other_pupil=other_pupil.id)
    return app, ids


def assign(client, ids, programme=None, pupil=None, **scope):
    return client.post('/teacher/interventions', data={**SCOPE, **scope, 'action':'assign_programme',
        'programme_id': programme or ids['programme'], 'pupil_id': pupil or ids['pupils'][0]})


@pytest.mark.parametrize('method', ['get', 'post'])
def test_only_admin_can_manage_library(library, method):
    app, ids = library; client = app.test_client(); login(client, ids['teacher'])
    assert getattr(client, method)('/admin/intervention-programmes').status_code == 403


def test_admin_create_edit_and_case_insensitive_duplicate(library):
    app, ids = library; client = app.test_client(); login(client, ids['admin'])
    data = {'name':'Comprehension club', 'subject':'reading', 'description':'Two short sessions each week'}
    assert client.post('/admin/intervention-programmes', data=data).status_code == 302
    with app.app_context():
        programme = InterventionProgramme.query.filter_by(name='Comprehension club').one()
        pid = programme.id; assert programme.school_id == ids['a']
    assert client.post('/admin/intervention-programmes', data={**data,'name':' comprehension CLUB '}).status_code == 302
    with app.app_context(): assert InterventionProgramme.query.filter_by(name_key='comprehension club').count() == 1
    client.post('/admin/intervention-programmes', data={**data,'programme_id':pid,'name':'Comprehension support'})
    with app.app_context(): assert db.session.get(InterventionProgramme,pid).name == 'Comprehension support'


@pytest.mark.parametrize('changes', [{'subject':'science'}, {'name':''}, {'name':'x'*121}, {'description':'x'*2001}])
def test_admin_invalid_programmes_do_not_create_rows(library, changes):
    app,ids=library;client=app.test_client();login(client,ids['admin'])
    client.post('/admin/intervention-programmes',data={'name':'New group','subject':'maths',**changes})
    with app.app_context(): assert InterventionProgramme.query.count()==4


def test_admin_cannot_see_or_modify_other_school_programme(library):
    app,ids=library;client=app.test_client();login(client,ids['admin'])
    assert b'Private booster' not in client.get('/admin/intervention-programmes').data
    assert client.post('/admin/intervention-programmes',data={'action':'toggle','programme_id':ids['foreign_programme']}).status_code==404
    assert client.post('/admin/intervention-programmes',data={'programme_id':ids['foreign_programme'],'name':'Tampered','subject':'maths'}).status_code==404


def test_programme_assignment_is_idempotent_and_preserves_notes_and_assessments(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    for programme in [ids['programme'],ids['programme'],ids['second_programme']]: assert assign(client,ids,programme).status_code==302
    with app.app_context():
        record=db.session.get(Intervention,ids['record'])
        assert Intervention.query.count()==1 and len(record.programmes)==2
        assert record.note=='Keep existing plan' and record.auto_flagged
        assert SubjectResult.query.count()==0
        assert {a.school_id for a in record.programme_assignments}=={ids['a']}


@pytest.mark.parametrize('bad_choice', ['foreign_programme','reading_programme','other_pupil','same_school_other_pupil'])
def test_assignment_rejects_foreign_school_class_or_subject(library,bad_choice):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    assign(client,ids,programme=ids[bad_choice] if 'programme' in bad_choice else None,
           pupil=ids[bad_choice] if 'pupil' in bad_choice else None)
    with app.app_context(): assert InterventionProgrammeAssignment.query.count()==0


def test_teacher_can_assign_any_own_pupil_without_auto_flag(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    assign(client,ids,pupil=ids['pupils'][1])
    with app.app_context():
        record=Intervention.query.filter_by(pupil_id=ids['pupils'][1]).one()
        assert record.is_active and not record.auto_flagged and len(record.programmes)==1


def test_archiving_blocks_new_assignments_but_preserves_old_groups(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    login(client,ids['admin']);client.post('/admin/intervention-programmes',data={'action':'toggle','programme_id':ids['programme']})
    login(client,ids['teacher']);assign(client,ids,pupil=ids['pupils'][1])
    page=client.get('/teacher/interventions',query_string=SCOPE)
    assert b'Archived programme' in page.data and b'Maths booster' in page.data
    with app.app_context(): assert InterventionProgrammeAssignment.query.count()==1


def test_remove_assignment_keeps_intervention_plan_and_other_programme(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    assign(client,ids);assign(client,ids,ids['second_programme'])
    client.post('/teacher/interventions',data={**SCOPE,'action':'remove_programme','record_id':ids['record'],'programme_id':ids['programme']})
    with app.app_context():
        record=db.session.get(Intervention,ids['record'])
        assert record.note=='Keep existing plan' and record.is_active
        assert [p.id for p in record.programmes]==[ids['second_programme']]


def test_closing_is_respected_on_result_resync_and_reopening_is_explicit(library):
    from app.services.assessments import get_subject_setting
    from app.services.assessment_reliability import apply_result
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    client.post('/teacher/interventions',data={**SCOPE,'action':'close','record_id':ids['record']})
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher']))
        pupil=db.session.get(Pupil,ids['pupils'][0]);setting=get_subject_setting(5,'maths','autumn','2026/27')
        result=SubjectResult(pupil=pupil,school_id=ids['a'],**SCOPE);db.session.add(result)
        apply_result(result,setting,10,10);db.session.flush()
        sync_auto_interventions(db.session.get(SchoolClass,ids['ca']),'maths','autumn','2026/27',55);db.session.commit()
        record=db.session.get(Intervention,ids['record']);assert not record.is_active and record.closed_by_teacher
        assert len(record.programmes)==1 and record.note=='Keep existing plan'
    client.post('/teacher/interventions',data={**SCOPE,'action':'reopen','record_id':ids['record']})
    with app.app_context(): assert db.session.get(Intervention,ids['record']).is_active


def test_assigned_auto_programme_is_not_closed_when_score_improves(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher']))
        sync_auto_interventions(db.session.get(SchoolClass,ids['ca']),'maths','autumn','2026/27',55);db.session.commit()
        assert db.session.get(Intervention,ids['record']).is_active


def test_scores_are_exact_term_and_zero_is_not_missing(library):
    app,ids=library
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher']))
        record=db.session.get(Intervention,ids['record'])
        db.session.add(SubjectResult(pupil_id=record.pupil_id,school_id=ids['a'],subject='maths',term='spring',academic_year='2026/27',combined_percent=90))
        db.session.flush();assert get_current_score_for_intervention(record)=='—'
        db.session.add(SubjectResult(pupil_id=record.pupil_id,school_id=ids['a'],**SCOPE,combined_percent=0,combined_score=0))
        db.session.flush();metric=intervention_assessment(record)
        assert metric['score'].startswith('0%') and metric['gap']>0


def test_filters_apply_to_csv_and_programmes_are_included(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    with app.app_context():
        db.session.add(Intervention(pupil_id=ids['pupils'][1],school_id=ids['a'],reason='Do not export this',subject='reading',term='spring',academic_year='2026/27',is_active=True));db.session.commit()
    login(client,ids['admin'])
    query={**SCOPE,'status':'active','programme_id':ids['programme'],'class_id':ids['ca'],'year_group':'5','anon':'1'}
    response=client.get('/admin/exports/interventions',query_string=query)
    assert response.status_code==200
    rows=list(csv.DictReader(io.StringIO(response.data.decode())))
    assert len(rows)==1 and rows[0]['programmes']=='Maths booster' and rows[0]['pupil_name']=='Pupil 1'
    page=client.get('/admin/interventions',query_string=query)
    assert page.status_code==200 and b'Do not export this' not in page.data


def test_teacher_pages_preserve_data_and_offer_menu_and_dragdrop(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    for status in ['active','closed','all']:
        response=client.get('/teacher/interventions',query_string={**SCOPE,'status':status})
        assert response.status_code==200 and b'Private booster' not in response.data
    response=client.get('/teacher/interventions',query_string=SCOPE)
    assert b'data-programme-drop' in response.data and b'name="programme_id"' in response.data
    with app.app_context():
        assert Intervention.query.count()==1 and InterventionProgrammeAssignment.query.count()==1
        assert db.session.get(Intervention,ids['record']).note=='Keep existing plan'


def test_programme_and_quick_save_require_csrf(library):
    app,ids=library;app.config['WTF_CSRF_ENABLED']=True;client=app.test_client();login(client,ids['admin'])
    assert client.post('/admin/intervention-programmes',data={'name':'New','subject':'maths'}).status_code==400
    login(client,ids['teacher'])
    assert assign(client,ids).status_code==400
    assert client.post('/teacher/api/interventions/quick-save',json={'record_id':ids['record'],'field':'note','value':'no token'}).status_code==400


@pytest.mark.parametrize('value',['false','true',0,None,[],{}])
def test_quick_save_requires_boolean_status(library,value):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    assert client.post('/teacher/api/interventions/quick-save',json={'record_id':ids['record'],'field':'is_active','value':value}).status_code==400
    with app.app_context(): assert db.session.get(Intervention,ids['record']).is_active


def test_deleting_pupil_removes_assignments_but_keeps_catalogue(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    with app.app_context():
        db.session.delete(db.session.get(Pupil,ids['pupils'][0]));db.session.commit()
        assert InterventionProgrammeAssignment.query.count()==0
        assert InterventionProgramme.query.count()==4


def test_closed_record_and_assignment_stay_in_their_term_and_year(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    assert b'Maths booster' in client.get('/teacher/interventions',query_string=SCOPE).data
    for scope in [{'term':'spring'}, {'academic_year':'2025/26'}]:
        page=client.get('/teacher/interventions',query_string={**SCOPE,**scope})
        assert b'Keep existing plan' not in page.data
        response=client.post('/teacher/interventions',data={**SCOPE,**scope,'action':'close','record_id':ids['record']})
        assert response.status_code==404
    with app.app_context(): assert db.session.get(Intervention,ids['record']).is_active


def test_http_pupil_delete_removes_assignment_without_other_school_damage(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids)
    with app.app_context():
        pupil=db.session.get(Pupil,ids['pupils'][0]);pupil.is_archived=True;db.session.commit()
    login(client,ids['admin'])
    assert client.post(f'/admin/archive/pupils/{ids["pupils"][0]}/delete',data={'confirm_delete_text':'DELETE'}).status_code==302
    with app.app_context():
        assert InterventionProgrammeAssignment.query.count()==0
        assert db.session.get(Pupil,ids['other_pupil']) is not None
        assert InterventionProgramme.query.count()==4


def test_manual_programme_does_not_gain_duplicate_auto_intervention(library):
    from app.services.assessments import get_subject_setting
    from app.services.assessment_reliability import apply_result
    app,ids=library;client=app.test_client();login(client,ids['teacher']);assign(client,ids,pupil=ids['pupils'][1])
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher']))
        pupil=db.session.get(Pupil,ids['pupils'][1]);result=SubjectResult(pupil=pupil,school_id=ids['a'],**SCOPE)
        db.session.add(result);apply_result(result,get_subject_setting(5,'maths','autumn','2026/27'),10,10);db.session.flush()
        sync_auto_interventions(db.session.get(SchoolClass,ids['ca']),'maths','autumn','2026/27',55);db.session.commit()
        assert Intervention.query.filter_by(pupil_id=pupil.id).count()==1


def test_closest_six_use_gap_to_each_saved_threshold(library):
    from app.services.interventions import suggest_interventions_for_scope
    app,ids=library
    with app.app_context():
        for index in range(7):
            pupil=Pupil(school_id=ids['a'],class_id=ids['ca'],first_name=f'Candidate {index}',last_name='Fictional',gender='Male',is_active=True)
            db.session.add(pupil);db.session.flush()
            threshold,score=(90,80) if index==0 else (50,49)
            db.session.add(SubjectResult(pupil=pupil,school_id=ids['a'],**SCOPE,combined_percent=score,
                                        configuration_snapshot={'below_are_threshold_percent':threshold}))
        db.session.flush()
        suggestions=suggest_interventions_for_scope(db.session.get(SchoolClass,ids['ca']),'maths','autumn','2026/27',55)
        assert len(suggestions)==6 and all(item['gap_to_pass']==1 for item in suggestions)


def test_legacy_update_does_not_clear_missing_fields(library):
    app,ids=library;client=app.test_client();login(client,ids['teacher'])
    client.post('/teacher/interventions',data={**SCOPE,'action':'update'})
    with app.app_context(): assert db.session.get(Intervention,ids['record']).note=='Keep existing plan'
