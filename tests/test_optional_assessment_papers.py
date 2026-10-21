"""Single-paper assessments, preservation and review/confirm regressions."""
import io
from types import SimpleNamespace
import pytest
from flask_login import login_user
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect, text
from test_assessment_reliability import world, login
from app.extensions import db
from app.models import AssessmentConfiguration, AssessmentReview, Pupil, SubjectResult, User
from app.services.assessments import AssessmentValidationError, compute_subject_result_values, get_setting_defaults, get_subject_setting, validate_setting_payload
from app.services.assessment_reliability import apply_result, assessment_health, configuration_values, school_fingerprint, setting_for_result


def config(ids, enabled=1):
    values=get_setting_defaults('maths') | {'paper_1_enabled':enabled==1,'paper_2_enabled':enabled==2,'combined_max':40 if enabled==1 else 35}
    row=AssessmentConfiguration(school_id=ids['a'],academic_year='2026/27',year_group=5,subject='maths',term='autumn',**values)
    db.session.add(row);db.session.commit();return row


@pytest.mark.parametrize('enabled,first,second,total,pct',[(1,20,None,20,50),(2,None,35,35,100),(1,0,None,0,0),(2,None,0,0,0),(1,None,20,None,None),(2,20,None,None,None),(1,20,999,20,50)])
def test_only_enabled_papers_are_required_and_count(enabled,first,second,total,pct):
    values=get_setting_defaults('maths')|{'paper_1_enabled':enabled==1,'paper_2_enabled':enabled==2,'combined_max':40 if enabled==1 else 35}
    result=compute_subject_result_values(SimpleNamespace(**values),first,second)
    assert result['combined_score']==total and result['combined_percent']==pct


def test_both_papers_cannot_be_disabled():
    with pytest.raises(AssessmentValidationError,match='at least one'):
        validate_setting_payload(get_setting_defaults('maths')|{'paper_1_enabled':False,'paper_2_enabled':False,'combined_max':None})


def test_old_snapshots_continue_to_require_both_papers():
    old=SimpleNamespace(**get_setting_defaults('maths'))
    assert compute_subject_result_values(old,40,None)['combined_score'] is None
    assert configuration_values(old)['paper_2_enabled'] is True


def test_setup_preview_then_confirm_keeps_marks_and_other_year(world):
    app,ids=world
    with app.app_context():
        pupil=db.session.get(Pupil,ids['pupils'][0])
        for year in ('2025/26','2026/27'):
            r=SubjectResult(pupil=pupil,school_id=ids['a'],academic_year=year,subject='maths',term='autumn')
            db.session.add(r)
            apply_result(r,SimpleNamespace(school_id=ids['a'],**get_setting_defaults('maths')),30,5,cohort=5,assessment_year_group=5)
        db.session.commit()
    client=app.test_client();login(client,ids['admin'])
    payload={'academic_year':'2026/27','year_group':'5','subject':'maths','term':'autumn','paper_1_name':'Arithmetic','paper_1_max':'40','paper_2_name':'Reasoning','paper_2_max':'35','paper_1_enabled':'yes','paper_2_enabled':'no','below_are_threshold_percent':'55','exceeding_threshold_percent':'80'}
    preview=client.post('/admin/assessments/setup',data=payload);assert preview.status_code==302
    page=client.get(preview.location);assert b'Use Paper 2' in page.data and b'Off' in page.data
    with app.app_context():
        assert AssessmentConfiguration.query.count()==0
        assert SubjectResult.query.filter_by(academic_year='2026/27').one().combined_score==35
    assert client.post(preview.location,data={'action':'apply'}).status_code==302
    with app.app_context():
        current=SubjectResult.query.filter_by(academic_year='2026/27').one()
        assert current.paper_2_score==5 and current.combined_score==30 and current.combined_percent==75
        assert current.configuration_snapshot['paper_2_enabled'] is False
        assert SubjectResult.query.filter_by(academic_year='2025/26').one().combined_score==35
        assert AssessmentConfiguration.query.one().paper_2_max==35
    # Re-enable without losing the saved second-paper mark.
    payload['paper_2_enabled']='yes'
    preview=client.post('/admin/assessments/setup',data=payload)
    assert client.post(preview.location,data={'action':'apply'}).status_code==302
    with app.app_context():
        current=SubjectResult.query.filter_by(academic_year='2026/27').one()
        assert current.paper_2_score==5 and current.combined_score==35


@pytest.mark.parametrize('enabled',[1,2])
def test_manual_entry_and_live_calculation_with_one_paper(world,enabled):
    app,ids=world
    with app.app_context():config(ids,enabled);baseline=school_fingerprint(ids['a'])
    client=app.test_client();login(client,ids['teacher']);pid=ids['pupils'][0]
    page=client.get('/teacher/maths?academic_year=2026/27&term=autumn')
    assert page.status_code==200 and b'Not used' in page.data
    data={'form_name':'results','academic_year':'2026/27','term':'autumn','baseline':baseline,f'paper_{enabled}_score_{pid}':'0',f'assessment_year_group_{pid}':'5'}
    response=client.post('/teacher/maths',data=data,follow_redirects=True)
    assert response.status_code==200 and b'All changes saved' in response.data
    with app.app_context():
        result=SubjectResult.query.one()
        assert result.combined_score==0 and result.combined_percent==0
        assert getattr(result,f'paper_{3-enabled}_score') is None
        pupil=db.session.get(Pupil,pid)
        assert assessment_health([pupil],{pid:result},get_subject_setting(5,'maths','autumn','2026/27',school_id=ids['a']))['label']=='Complete'
    response=client.post('/teacher/maths/calculate',json={'academic_year':'2026/27','term':'autumn','rows':[{'pupil_id':pid,f'paper_{enabled}_score':20,'assessment_year_group':5}]})
    assert response.status_code==200,response.status_code
    assert response.json['rows'][0]['combined_score']==20


@pytest.mark.parametrize('enabled',[1,2])
def test_single_column_csv_preview_and_confirmation(world,enabled):
    app,ids=world
    with app.app_context():config(ids,enabled)
    client=app.test_client();login(client,ids['teacher']);pid=ids['pupils'][0]
    raw=f'pupil_id,paper_{enabled}_score\n{pid},20\n'.encode()
    preview=client.post('/teacher/maths/upload',data={'academic_year':'2026/27','term':'autumn','csv_file':(io.BytesIO(raw),'one-paper.csv')})
    assert preview.status_code==302
    page=client.get(preview.location);assert b'0 blocking problems' in page.data
    assert client.post(preview.location,data={'action':'apply'}).status_code==302
    with app.app_context():
        result=SubjectResult.query.one()
        assert result.combined_score==20 and result.combined_percent==round(2000/(40 if enabled==1 else 35),1)


def test_disabled_mark_is_preserved_on_subsequent_manual_save(world):
    app,ids=world
    with app.app_context():
        setting=config(ids,1);pupil=db.session.get(Pupil,ids['pupils'][0])
        result=SubjectResult(pupil=pupil,school_id=ids['a'],academic_year='2026/27',subject='maths',term='autumn',paper_2_score=15)
        db.session.add(result);apply_result(result,setting,20,None);db.session.commit()
        assert result.paper_2_score==15
        baseline=school_fingerprint(ids['a'])
    client=app.test_client();login(client,ids['teacher']);pid=ids['pupils'][0]
    assert client.post('/teacher/maths',data={'form_name':'results','academic_year':'2026/27','term':'autumn','baseline':baseline,f'paper_1_score_{pid}':'30',f'assessment_year_group_{pid}':'5'}).status_code==302
    with app.app_context():assert SubjectResult.query.one().paper_2_score==15


def test_migration_keeps_existing_configuration_and_results(world):
    app,ids=world
    with app.app_context():
        configured=config(ids,1)
        configured.paper_2_enabled=True
        configured.combined_max=75
        db.session.commit()
        db.session.add(SubjectResult(school_id=ids['a'],pupil_id=ids['pupils'][0],academic_year='2026/27',subject='maths',term='autumn',paper_1_score=20,paper_2_score=10,combined_score=30,combined_percent=40,band_label='Working Towards'))
        db.session.commit()
        # Recreate the exact pre-feature column set in this disposable DB.
        db.session.execute(text('ALTER TABLE assessment_configurations DROP COLUMN paper_1_enabled'))
        db.session.execute(text('ALTER TABLE assessment_configurations DROP COLUMN paper_2_enabled'));db.session.commit()
        stamp(revision='20261005_01');upgrade()
        db.session.expire_all();row=AssessmentConfiguration.query.one()
        assert row.paper_1_enabled is True and row.paper_2_enabled is True
        assert row.paper_1_max==40 and row.paper_2_max==35 and row.combined_max==75
        result=SubjectResult.query.one()
        assert (result.paper_1_score,result.paper_2_score,result.combined_score,result.combined_percent,result.band_label)==(20,10,30,40,'Working Towards')


@pytest.mark.parametrize('enabled',[1,2])
def test_workbook_uses_only_enabled_paper(world,enabled):
    import base64
    from openpyxl import Workbook
    from app.services.assessment_imports import simulate_import,process_import
    app,ids=world
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['admin']));config(ids,enabled)
        wb=Workbook();ws=wb.active;ws.title='Maths'
        ws.append(['pupil_id','pupil','class','term','arithmetic','reasoning'])
        ws.append([ids['pupils'][0],'Alice Test','Oak','autumn',20 if enabled==1 else None,20 if enabled==2 else None])
        buffer=io.BytesIO();wb.save(buffer)
        payload={'school_id':ids['a'],'academic_year':'2026/27','workbook':base64.b64encode(buffer.getvalue()).decode()}
        report=simulate_import('workbook',payload);assert not report['errors'],report
        assert SubjectResult.query.count()==0
        process_import('workbook',payload);db.session.commit()
        assert SubjectResult.query.one().combined_score==20
        assert SubjectResult.query.one().combined_percent==round(2000/(40 if enabled==1 else 35),1)


@pytest.mark.parametrize('enabled',[1,2])
def test_csv_template_omits_disabled_column(world,enabled):
    app,ids=world
    with app.app_context():config(ids,enabled)
    client=app.test_client();login(client,ids['teacher'])
    r=client.get('/teacher/maths/import-template.csv?academic_year=2026/27&term=autumn')
    assert r.status_code==200
    header=r.data.decode().splitlines()[0]
    assert f'paper_{enabled}_score' in header and f'paper_{3-enabled}_score' not in header


def test_single_paper_results_are_complete_in_admin_summary(world):
    from flask import template_rendered
    app,ids=world
    with app.app_context():
        pupil=db.session.get(Pupil,ids['pupils'][0])
        for subject in ('maths','reading','spag'):
            values=get_setting_defaults(subject)|{'paper_1_enabled':True,'paper_2_enabled':False}
            values['combined_max']=values['paper_1_max']
            setting=AssessmentConfiguration(school_id=ids['a'],academic_year='2026/27',year_group=5,subject=subject,term='autumn',**values)
            row=SubjectResult(pupil=pupil,school_id=ids['a'],academic_year='2026/27',subject=subject,term='autumn')
            db.session.add_all([setting,row]);apply_result(row,setting,0,None)
        db.session.commit()
    captured=[]
    def capture(sender,template,context,**extra):captured.append(context)
    template_rendered.connect(capture,app)
    try:
        client=app.test_client();login(client,ids['admin'])
        assert client.get('/admin/data-quality?academic_year=2026/27&term=autumn').status_code==200
    finally:template_rendered.disconnect(capture,app)
    issue=next(x for x in captured[-1]['issues'] if x['issue'].startswith('Missing scores for'))
    assert issue['count']==1  # Only the second pupil is missing results.
