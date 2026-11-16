"""/healthz is a tiny public 'is it awake' check. Fictional data only."""
from test_assessment_reliability import login, world  # noqa: F401


def test_healthz_is_public_plain_and_uncached(world):  # noqa: F811
    app, ids = world
    response = app.test_client().get('/healthz')
    assert response.status_code == 200 and response.get_data(as_text=True) == 'ok'
    assert response.mimetype == 'text/plain' and response.headers['Cache-Control'] == 'no-store'


def test_healthz_shows_nothing_about_schools_or_pupils(world):  # noqa: F811
    app, ids = world
    text = app.test_client().get('/healthz').get_data(as_text=True)
    assert 'School' not in text and 'Alice' not in text


def test_healthz_works_for_a_user_who_must_change_password(world):  # noqa: F811
    from app.extensions import db
    from app.models import User
    app, ids = world
    with app.app_context():
        db.session.get(User, ids['teacher']).require_password_change = True
        db.session.commit()
    client = app.test_client(); login(client, ids['teacher'])
    assert client.get('/healthz').status_code == 200
