"""The site can be added to an iPad home screen. Fictional data only."""
import pathlib

from test_assessment_reliability import login, world  # noqa: F401

STATIC = pathlib.Path(__file__).parents[1] / 'app' / 'static'


def test_manifest_is_public_valid_and_points_at_real_icons(world):  # noqa: F811
    app, ids = world
    response = app.test_client().get('/manifest.webmanifest')
    assert response.status_code == 200 and response.mimetype == 'application/manifest+json'
    data = response.get_json()
    assert data['display'] == 'standalone' and data['name'] == 'Class Compass' and data['start_url'] == '/dashboard'
    assert {icon['sizes'] for icon in data['icons']} == {'192x192', '512x512'}
    assert any(icon['purpose'] == 'maskable' for icon in data['icons'])
    for icon in data['icons']:
        assert (STATIC / icon['src'].removeprefix('/static/')).is_file(), icon['src']


def test_manifest_has_no_school_or_pupil_data(world):  # noqa: F811
    app, ids = world
    text = app.test_client().get('/manifest.webmanifest').get_data(as_text=True)
    assert 'School A' not in text and 'Alice' not in text


def test_pages_link_the_manifest_and_apple_tags(world):  # noqa: F811
    app, ids = world
    client = app.test_client(); login(client, ids['teacher'])
    html = client.get('/dashboard/teacher').get_data(as_text=True)
    for expected in ('rel="manifest"', 'apple-touch-icon', 'apple-mobile-web-app-capable', 'viewport-fit=cover'):
        assert expected in html, expected
    assert (STATIC / 'icons' / 'apple-touch-icon.png').is_file()
