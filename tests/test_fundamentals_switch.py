"""Maths Fundamentals can be switched off without deleting anything. Fictional data only."""
from test_assessment_reliability import login, world  # noqa: F401

PAGES = ['/fundamentals/', '/fundamentals/start', '/fundamentals/scores', '/fundamentals/levels',
         '/fundamentals/interventions', '/fundamentals/join/not-a-real-token', '/fundamentals/pupil/question/not-a-real-token']


def test_every_fundamentals_page_is_not_found_when_switched_off(world):  # noqa: F811
    app, ids = world
    app.config['FUNDAMENTALS_ENABLED'] = False
    client = app.test_client(); login(client, ids['teacher'])
    for page in PAGES:
        assert client.get(page).status_code == 404, page
    anonymous = app.test_client()
    assert anonymous.get('/fundamentals/join/not-a-real-token').status_code == 404


def test_menu_link_is_hidden_when_off_and_shown_when_on(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    app.config['FUNDAMENTALS_ENABLED'] = False
    assert b'Maths Fundamentals' not in client.get('/dashboard/teacher').data
    app.config['FUNDAMENTALS_ENABLED'] = True
    assert b'Maths Fundamentals' in client.get('/dashboard/teacher').data


def test_the_site_default_is_off():
    """A fresh process with no setting must come up with the feature off."""
    import os, pathlib, subprocess, sys
    env = {key: value for key, value in os.environ.items() if key != 'FUNDAMENTALS_ENABLED'}
    root = pathlib.Path(__file__).parents[1]
    result = subprocess.run([sys.executable, '-c', 'import config; print(config.Config.FUNDAMENTALS_ENABLED)'],
                            cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == 'False', result.stderr
