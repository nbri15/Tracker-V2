"""Fictional, disposable regression coverage for the final pilot blockers."""
import pytest
from flask import template_rendered
from werkzeug.datastructures import MultiDict
from test_assessment_reliability import world, login
from app import create_app
from app.extensions import db
from app.models import GapTemplate, GapQuestion, GapScore, Pupil, SubjectResult, User, Intervention
from app.services.gap import parse_question_columns, save_gap_scores
from app.services.assessments import AssessmentValidationError
from config import Config, ProductionConfig, config_by_name
from flask_login import login_user


def make_gap(ids):
    template = GapTemplate(school_id=ids['a'],year_group=5,subject='maths',term='autumn',academic_year='2026/27')
    q = GapQuestion(template=template,school_id=ids['a'],question_label='1',question_type='Addition',max_score=20,paper_key='paper_1',display_order=0)
    db.session.add(template); db.session.flush()
    db.session.add(GapScore(school_id=ids['a'],pupil_id=ids['pupils'][0],question_id=q.id,score=10)); db.session.commit()
    return template,q


def definition(questions, **changes):
    data=MultiDict()
    for q in questions:
        for key,value in [('question_id[]',q.id),('question_paper[]',q.paper_key),('question_label[]',q.question_label),('question_type[]',q.question_type or ''),('question_max[]',q.max_score)]:
            data.add(key,str(changes.get(key,value)))
    return data


@pytest.mark.parametrize('secret',[None,'','dev-secret-key-change-me'])
def test_production_rejects_missing_or_development_secret(monkeypatch, secret):
    class BadProduction(Config):
        ENV='production'
        SECRET_KEY=secret
    monkeypatch.setitem(config_by_name,'pilot-prod',BadProduction)
    with pytest.raises(RuntimeError,match='private SECRET_KEY'):
        create_app('pilot-prod')


def test_production_accepts_private_key_and_hardens_cookies(tmp_path, monkeypatch):
    class SafeProduction(ProductionConfig):
        ENV='production'; SECRET_KEY='fictional-pilot-secret-not-for-production'
        ALLOW_DEV_BOOTSTRAP=False
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path / "startup.db"}'
        SQLALCHEMY_ENGINE_OPTIONS={}
    monkeypatch.setitem(config_by_name,'pilot-prod',SafeProduction)
    app=create_app('pilot-prod')
    from sqlalchemy import inspect
    with app.app_context(): assert inspect(db.engine).get_table_names()==[]
    for cookie in ('SESSION','REMEMBER'):
        assert app.config[cookie+'_COOKIE_HTTPONLY'] is True
        assert app.config[cookie+'_COOKIE_SECURE'] is True
        assert app.config[cookie+'_COOKIE_SAMESITE']=='Lax'


def test_teacher_cannot_change_definitions_but_can_save_marks(world):
    app,ids=world
    with app.app_context():
        template,q=make_gap(ids); qid=q.id
        data=definition([q]); data.update({'action':'save_gap','academic_year':'2026/27','term':'autumn',f'score_{ids["pupils"][0]}_{qid}':'0'})
    client=app.test_client();login(client,ids['teacher'])
    assert client.post('/admin/gap-templates',data=data).status_code==403
    assert client.post('/teacher/maths/gap',data={'action':'add_question','academic_year':'2026/27','term':'autumn','new_question_label':'hack','new_question_max':'1'}).status_code==403
    assert client.post('/teacher/maths/gap',data=data).status_code==302
    with app.app_context():
        assert GapScore.query.one().score==0
        assert db.session.get(GapQuestion,qid).max_score==20
    data.setlist('question_max[]',['1'])
    assert client.post('/teacher/maths/gap',data=data).status_code==200
    with app.app_context():
        assert db.session.get(GapQuestion,qid).max_score==20
        assert GapScore.query.one().score==0


def test_admin_edit_preserves_ids_marks_and_adds_question(world):
    app,ids=world
    with app.app_context():
        template,q=make_gap(ids); qid=q.id; sid=GapScore.query.one().id
        data=definition([q],**{'question_label[]':'1a'})
        for key,value in [('question_id[]',''),('question_paper[]','paper_1'),('question_label[]','2'),('question_type[]','Subtraction'),('question_max[]','20')]:data.add(key,value)
    data.update({'academic_year':'2026/27','year_group':'5','subject':'maths','term':'autumn'})
    client=app.test_client();login(client,ids['admin'])
    assert client.get('/admin/gap-templates').status_code==200
    assert client.post('/admin/gap-templates',data=data).status_code==302
    with app.app_context():
        assert GapQuestion.query.count()==2
        assert db.session.get(GapQuestion,qid).question_label=='1a'
        assert db.session.get(GapScore,sid).score==10
        assert db.session.get(GapScore,sid).question_id==qid


@pytest.mark.parametrize('change',[{'question_max[]':'5'},{'question_paper[]':'paper_2'},{'question_id[]':'999999'}])
def test_unsafe_definition_edit_is_rejected_without_loss(world,change):
    app,ids=world
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['admin']))
        template,q=make_gap(ids); qid=q.id
        with pytest.raises(AssessmentValidationError): parse_question_columns(definition([q],**change),template)
        db.session.rollback()
        assert GapScore.query.one().score==10
        assert db.session.get(GapQuestion,qid).max_score==20


def test_scored_question_cannot_be_omitted_or_replaced(world):
    app,ids=world
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['admin'])); template,q=make_gap(ids)
        data=definition([q],**{'question_id[]':'','question_label[]':'replacement'})
        with pytest.raises(AssessmentValidationError,match='cannot be removed'):parse_question_columns(data,template)
        db.session.rollback(); assert GapScore.query.one().score==10


def test_partial_gap_submission_retains_omitted_marks_and_correct_total(world):
    app,ids=world
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher'])); template,q1=make_gap(ids)
        q2=GapQuestion(template=template,school_id=ids['a'],question_label='2',max_score=20,paper_key='paper_1',display_order=1)
        db.session.add(q2);db.session.flush()
        db.session.add(GapScore(school_id=ids['a'],pupil_id=ids['pupils'][0],question_id=q2.id,score=10));db.session.commit()
        pupil=db.session.get(Pupil,ids['pupils'][0])
        outcome=save_gap_scores([pupil],[q1,q2],{f'score_{pupil.id}_{q1.id}':'15'},school_id=ids['a'])
        db.session.commit()
        assert GapScore.query.count()==2
        assert outcome['pupil_totals'][pupil.id]==25
        assert SubjectResult.query.one().paper_1_score==25


@pytest.mark.parametrize('raw',['-1','21','nan','inf','nope'])
def test_invalid_gap_mark_rolls_back_the_whole_save(world,raw):
    app,ids=world
    with app.app_context():
        template,q=make_gap(ids); data=definition([q]); qid=q.id
    data.update({'action':'save_gap','academic_year':'2026/27','term':'autumn',f'score_{ids["pupils"][0]}_{qid}':'15',f'score_{ids["pupils"][1]}_{qid}':raw})
    client=app.test_client();login(client,ids['teacher'])
    assert client.post('/teacher/maths/gap',data=data).status_code==200
    with app.app_context():
        assert GapScore.query.one().score==10
        assert SubjectResult.query.count()==0


def test_admin_foreign_question_and_teacher_foreign_scores_are_blocked(world):
    app,ids=world
    with app.app_context():
        template,q=make_gap(ids); data=definition([q]); qid=q.id
    client=app.test_client();login(client,ids['other'])
    data.update({'action':'save_gap','academic_year':'2026/27','term':'autumn',f'score_{ids["pupils"][0]}_{qid}':'0'})
    client.post('/teacher/maths/gap',data=data)
    login(client,ids['admin'])
    data.update({'academic_year':'2026/27','year_group':'4','subject':'maths','term':'autumn'})
    r=client.post('/admin/gap-templates',data=data)
    assert r.status_code==200
    with app.app_context():
        assert GapScore.query.one().score==10
        assert GapTemplate.query.count()==1


@pytest.mark.parametrize('complete,expected',[(False,2),(True,1)])
def test_missing_scores_require_all_subjects_and_accept_zero(world, complete, expected):
    app,ids=world
    with app.app_context():
        for subject in (('maths','reading','spag') if complete else ('maths',)):
            db.session.add(SubjectResult(pupil_id=ids['pupils'][0],school_id=ids['a'],academic_year='2026/27',subject=subject,term='autumn',paper_1_score=0,paper_2_score=0 if complete else None,combined_percent=0 if complete else None,band_label='Working Towards' if complete else None))
        db.session.commit()
    captured=[]
    def capture(sender,template,context,**extra):captured.append(context)
    template_rendered.connect(capture,app)
    try:
        client=app.test_client();login(client,ids['admin'])
        assert client.get('/admin/data-quality?academic_year=2026/27&term=autumn').status_code==200
    finally:template_rendered.disconnect(capture,app)
    issue=next(x for x in captured[-1]['issues'] if x['issue'].startswith('Missing scores for'))
    assert issue['count']==expected


@pytest.mark.parametrize('role,path',[
    ('teacher','/teacher/maths'),('teacher','/teacher/reading'),('teacher','/teacher/spag'),
    ('teacher','/teacher/interventions'),('teacher','/dashboard/teacher'),('admin','/dashboard/admin'),
    ('admin','/admin/data-quality'),('admin','/admin/interventions'),('admin','/admin/imports'),
    ('admin','/admin/reports/headline'),('admin','/admin/reports/export-centre'),
    ('admin','/admin/exports/subject-results'),('admin','/admin/exports/interventions'),
])
def test_pilot_pages_and_exports_do_not_include_other_school(world,role,path):
    app,ids=world;client=app.test_client();login(client,ids[role])
    r=client.get(path+'?academic_year=2026/27&term=autumn',follow_redirects=True)
    assert r.status_code==200
    assert b'Other Pupil' not in r.data


def test_other_class_profile_and_intervention_edit_are_rejected(world):
    from app.models import SchoolClass
    app,ids=world
    with app.app_context():
        c=SchoolClass(school_id=ids['a'],name='Birch',year_group=4,is_active=True)
        p=Pupil(school_id=ids['a'],school_class=c,first_name='Private',last_name='Birch',gender='Male',is_active=True)
        intervention=Intervention(school_id=ids['a'],pupil=p,subject='maths',academic_year='2026/27',term='autumn',reason='Private reason',is_active=True)
        db.session.add_all([c,p,intervention]);db.session.commit();pid=p.id;iid=intervention.id
    client=app.test_client();login(client,ids['teacher'])
    assert client.get(f'/pupils/{pid}').status_code in (403,404)
    assert client.post('/teacher/api/interventions/quick-save',json={'record_id':iid,'field':'note','value':'tampered'}).status_code==404
    with app.app_context():assert db.session.get(Intervention,iid).note is None


def test_interventions_use_saved_threshold_and_never_reflag_on_get(world):
    from app.models import SchoolClass
    from app.services.assessments import get_subject_setting
    from app.services.assessment_reliability import apply_result
    from app.services.interventions import sync_auto_interventions
    app,ids=world
    with app.app_context(),app.test_request_context('/'):
        login_user(db.session.get(User,ids['teacher']))
        setting=get_subject_setting(5,'maths','autumn','2026/27')
        setting.below_are_threshold_percent=55
        setting.on_track_threshold_percent=55
        p=db.session.get(Pupil,ids['pupils'][0])
        result=SubjectResult(pupil=p,school_id=ids['a'],academic_year='2026/27',subject='maths',term='autumn')
        db.session.add(result)
        apply_result(result,setting,20,20)
        db.session.flush()
        # 40/75 < 55%; later live settings must not change the saved threshold.
        setting.below_are_threshold_percent=45
        setting.on_track_threshold_percent=45
        sync_auto_interventions(db.session.get(SchoolClass,ids['ca']),'maths','autumn','2026/27',45)
        db.session.commit();assert Intervention.query.one().is_active
        before=[(x.id,x.is_active,x.reason) for x in Intervention.query.all()]
    client=app.test_client();login(client,ids['teacher'])
    assert client.get('/teacher/interventions?academic_year=2026/27&term=autumn&subject=maths').status_code==200
    with app.app_context():assert [(x.id,x.is_active,x.reason) for x in Intervention.query.all()]==before


def test_populated_intervention_pdf_uses_existing_reason_and_is_school_scoped(world,monkeypatch):
    app,ids=world
    with app.app_context():
        for pid,school,reason in [(ids['pupils'][0],ids['a'],'Number facts'),(ids['other_pupil'],ids['b'],'Other school private')]:
            db.session.add(Intervention(pupil_id=pid,school_id=school,subject='maths',academic_year='2026/27',term='autumn',reason=reason,is_active=True))
        db.session.commit()
    captured=[]
    def render_pdf(title,headers,rows,*args,**kwargs):
        captured.extend(rows);return 'rendered',200
    monkeypatch.setattr('app.admin.routes._render_table_pdf',render_pdf)
    client=app.test_client();login(client,ids['admin'])
    assert client.get('/admin/interventions?academic_year=2026/27&format=pdf').status_code==200
    assert len(captured)==1 and captured[0][3]=='Number facts'


def test_gap_admin_save_requires_csrf(world):
    app,ids=world;app.config['WTF_CSRF_ENABLED']=True
    client=app.test_client();login(client,ids['admin'])
    assert client.post('/admin/gap-templates',data={'year_group':5}).status_code==400
    with app.app_context():assert GapTemplate.query.count()==0


def test_postgresql_schema_and_driver_initialization():
    from sqlalchemy import create_engine
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    # Compile every mapped table without connecting or touching any database.
    for table in db.metadata.tables.values():
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for driver in ('psycopg','psycopg2'):
        engine=create_engine(f'postgresql+{driver}://fictional:fictional@localhost/disposable')
        assert engine.dialect.driver==driver
        engine.dispose()


def test_administrator_cannot_edit_foreign_school_gap_template(world):
    app,ids=world
    with app.app_context():
        foreign=GapTemplate(school_id=ids['b'],year_group=5,subject='maths',term='autumn',academic_year='2026/27')
        q=GapQuestion(template=foreign,school_id=ids['b'],question_label='Private question',max_score=10,paper_key='paper_1')
        db.session.add(foreign);db.session.commit();qid=q.id
        data=definition([q],**{'question_label[]':'tampered'})
    data.update({'school_id':str(ids['b']),'academic_year':'2026/27','year_group':'5','subject':'maths','term':'autumn'})
    client=app.test_client();login(client,ids['admin'])
    assert client.post('/admin/gap-templates',data=data).status_code==200
    assert b'Private question' not in client.get('/admin/gap-templates').data
    with app.app_context():
        assert db.session.get(GapQuestion,qid).question_label=='Private question'
        assert GapTemplate.query.count()==1
