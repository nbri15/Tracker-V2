"""School logins require a code; platform executives retain their own login."""
import pytest
from test_assessment_reliability import world
from app.extensions import db
from app.models import User, School


def assert_signed_out(client):
    with client.session_transaction() as session:
        assert '_user_id' not in session


@pytest.mark.parametrize('role',['school_admin','admin','teacher'])
@pytest.mark.parametrize('code',[None,'','   '])
def test_school_roles_cannot_login_without_code(world,role,code):
    app,ids=world
    with app.app_context():
        user=db.session.get(User,ids['admin']);user.role=role;db.session.commit()
    data={'username':'admin-a','password':'password123'}
    if code is not None:data['school_code']=code
    client=app.test_client();r=client.post('/auth/login',data=data)
    assert r.status_code==200
    assert b'must include their school code' in r.data
    assert_signed_out(client)


def test_admin_email_cannot_bypass_school_code(world):
    app,ids=world
    with app.app_context():
        db.session.get(User,ids['admin']).username='admin@example.test';db.session.commit()
    client=app.test_client()
    assert client.post('/auth/login',data={'username':'admin@example.test','password':'password123'}).status_code==200
    assert_signed_out(client)
    assert client.post('/auth/login',data={'school_code':'school-a','username':'admin@example.test','password':'password123'}).status_code==302
    with client.session_transaction() as session:assert session['_user_id']==str(ids['admin'])


@pytest.mark.parametrize('code',['wrong-school','school-b'])
def test_unknown_or_other_school_code_cannot_authenticate_admin(world,code):
    app,ids=world;client=app.test_client()
    assert client.post('/auth/login',data={'school_code':code,'username':'admin-a','password':'password123'}).status_code==200
    assert_signed_out(client)


@pytest.mark.parametrize('role',['school_admin','teacher'])
def test_correct_school_code_authenticates_school_accounts(world,role):
    app,ids=world
    username='admin-a' if role=='school_admin' else 'teacher-a'
    uid=ids['admin'] if role=='school_admin' else ids['teacher']
    client=app.test_client()
    assert client.post('/auth/login',data={'school_code':' SCHOOL-A ','username':username,'password':'password123'}).status_code==302
    with client.session_transaction() as session:assert session['_user_id']==str(uid)


def test_duplicate_usernames_resolve_only_inside_selected_school(world):
    app,ids=world
    with app.app_context():
        second=User(username='admin-a',role='school_admin',school_id=ids['b'],is_active=True)
        second.set_password('different-password');db.session.add(second);db.session.commit();second_id=second.id
    client=app.test_client()
    assert client.post('/auth/login',data={'school_code':'school-a','username':'admin-a','password':'different-password'}).status_code==200
    assert_signed_out(client)
    assert client.post('/auth/login',data={'school_code':'school-b','username':'admin-a','password':'different-password'}).status_code==302
    with client.session_transaction() as session:assert session['_user_id']==str(second_id)


def test_executive_login_without_code_is_not_shadowed_by_school_admin(world):
    app,ids=world
    with app.app_context():
        executive=User(username='admin-a',role='executive_admin',is_active=True)
        executive.set_password('executive-password');db.session.add(executive);db.session.commit();exec_id=executive.id
    # Same username as a school admin does not allow their password into this path.
    client=app.test_client()
    assert client.post('/auth/login',data={'username':'admin-a','password':'password123'}).status_code==200
    assert_signed_out(client)
    assert client.post('/auth/login',data={'username':'admin-a','password':'executive-password'}).status_code==302
    with client.session_transaction() as session:assert session['_user_id']==str(exec_id)


@pytest.mark.parametrize('state',['inactive-school','archived-school','inactive-user'])
def test_correct_code_still_rejects_inactive_accounts(world,state):
    app,ids=world
    with app.app_context():
        if state=='inactive-school':db.session.get(School,ids['a']).is_active=False
        elif state=='archived-school':db.session.get(School,ids['a']).is_archived=True
        else:db.session.get(User,ids['admin']).is_active=False
        db.session.commit()
    client=app.test_client()
    assert client.post('/auth/login',data={'school_code':'school-a','username':'admin-a','password':'password123'}).status_code==200
    assert_signed_out(client)


def test_login_page_describes_requirement_and_retains_csrf(world):
    app,ids=world;app.config['WTF_CSRF_ENABLED']=True
    client=app.test_client();r=client.get('/auth/login')
    assert b'Required for school administrators and teachers' in r.data
    assert b'optional for email login' not in r.data
    assert b'aria-describedby="school-code-help"' in r.data
    assert client.post('/auth/login',data={'school_code':'school-a','username':'admin-a','password':'password123'}).status_code==400
    assert_signed_out(client)
