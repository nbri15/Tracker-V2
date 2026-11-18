"""Password rules, failed-login limiting, redirect safety and session lifetime."""
import pytest
from test_assessment_reliability import world  # noqa: F401
from app.security import LoginThrottle, password_problem
from app.utils import safe_redirect_target

GOOD = {'school_code': 'school-a', 'username': 'teacher-a'}


# ---- password rules -------------------------------------------------------
@pytest.mark.parametrize('bad', ['short1', 'elevenchars', 'password12345', '123456789012', 'aaaaaaaaaaaaaa', 'Welcome-to-school', 'qwertyuiopasdf'])
def test_weak_passwords_are_rejected(bad):
    assert password_problem(bad, 'someone') is not None


def test_password_cannot_contain_username():
    assert password_problem('xx-jbloggs-xx-yy', 'jbloggs') is not None


@pytest.mark.parametrize('good', ['purple-tractor-lemon-42', 'Rivers Stone Marmalade Lamp'])
def test_strong_passphrases_are_accepted(good):
    assert password_problem(good, 'jbloggs') is None


# ---- throttle logic -------------------------------------------------------
def test_throttle_blocks_after_limit_and_expires():
    t = LoginThrottle(max_attempts=3, window_seconds=100, max_ip_attempts=50)
    for i in range(3):
        assert t.seconds_until_allowed('1.1.1.1', 'a', now=i) == 0
        t.record_failure('1.1.1.1', 'a', now=i)
    assert t.seconds_until_allowed('1.1.1.1', 'a', now=3) > 0
    assert t.seconds_until_allowed('1.1.1.1', 'other', now=3) == 0      # other account unaffected
    assert t.seconds_until_allowed('2.2.2.2', 'a', now=3) == 0          # other address unaffected
    assert t.seconds_until_allowed('1.1.1.1', 'a', now=200) == 0        # window passed


def test_throttle_success_clears_account_failures():
    t = LoginThrottle(max_attempts=3, window_seconds=100, max_ip_attempts=50)
    for i in range(2):
        t.record_failure('1.1.1.1', 'a', now=i)
    t.record_success('1.1.1.1', 'a')
    t.record_failure('1.1.1.1', 'a', now=5)
    assert t.seconds_until_allowed('1.1.1.1', 'a', now=6) == 0


def test_throttle_limits_one_address_guessing_many_accounts():
    t = LoginThrottle(max_attempts=3, window_seconds=100, max_ip_attempts=5)
    for i in range(5):
        t.record_failure('1.1.1.1', f'user{i}', now=i)
    assert t.seconds_until_allowed('1.1.1.1', 'brand-new', now=6) > 0


# ---- redirect safety ------------------------------------------------------
@pytest.mark.parametrize('target', ['https://evil.example', '//evil.example', '/\\evil.example', '\\\\evil.example', 'evil.example', 'javascript:alert(1)', '/ok\r\nSet-Cookie: x=1', None, ''])
def test_unsafe_redirects_fall_back(target):
    assert safe_redirect_target(target, '/home') == '/home'


def test_local_redirects_are_kept():
    assert safe_redirect_target('/admin/pupils?x=1', '/home') == '/admin/pupils?x=1'


# ---- through the real login route ----------------------------------------
def test_repeated_wrong_passwords_lock_out_even_the_right_password(world):  # noqa: F811
    app, ids = world
    client = app.test_client()
    for _ in range(app.config['LOGIN_MAX_ATTEMPTS']):
        assert client.post('/auth/login', data={**GOOD, 'password': 'wrong-wrong-wrong'}).status_code == 200
    blocked = client.post('/auth/login', data={**GOOD, 'password': 'password123'})
    assert blocked.status_code == 429
    with client.session_transaction() as session:
        assert '_user_id' not in session


def test_a_good_login_is_not_affected_by_failures_on_another_account(world):  # noqa: F811
    app, ids = world
    client = app.test_client()
    for _ in range(app.config['LOGIN_MAX_ATTEMPTS']):
        client.post('/auth/login', data={'school_code': 'school-a', 'username': 'admin-a', 'password': 'nope-nope-nope'})
    assert client.post('/auth/login', data={**GOOD, 'password': 'password123'}).status_code == 302


def test_login_ignores_external_next_url(world):  # noqa: F811
    app, ids = world
    for nxt in ('https://evil.example/x', '//evil.example/x', '/\\evil.example'):
        response = app.test_client().post(f'/auth/login?next={nxt}', data={**GOOD, 'password': 'password123'})
        assert response.status_code == 302
        assert 'evil.example' not in response.headers['Location']


def test_signed_in_session_is_permanent_so_it_times_out(world):  # noqa: F811
    app, ids = world
    client = app.test_client()
    client.post('/auth/login', data={**GOOD, 'password': 'password123'})
    with client.session_transaction() as session:
        assert session.permanent is True
    assert app.config['PERMANENT_SESSION_LIFETIME'].total_seconds() <= 8 * 3600


def test_change_password_rejects_weak_password(world):  # noqa: F811
    app, ids = world
    client = app.test_client()
    client.post('/auth/login', data={**GOOD, 'password': 'password123'})
    weak = client.post('/auth/change-password', data={'new_password': 'password12345', 'confirm_password': 'password12345'})
    assert weak.status_code == 200
    assert client.post('/auth/login', data={**GOOD, 'password': 'password123'}).status_code in (302, 200)
    strong = client.post('/auth/change-password', data={'new_password': 'purple-tractor-lemon-42', 'confirm_password': 'purple-tractor-lemon-42'})
    assert strong.status_code == 302
