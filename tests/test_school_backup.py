"""One-click school backup: contents, school isolation, safety and access."""
import csv
import io
import zipfile

from test_assessment_reliability import world, login  # noqa: F401
from app.extensions import db
from app.models import AuditLog, User
from app.services.school_backup import scoped_select, unscoped_tables, NOT_SCHOOL_DATA


def _download(app, ids, who='admin'):
    client = app.test_client()
    login(client, ids[who])
    return client.post('/admin/backup/download')


def _zip(response):
    return zipfile.ZipFile(io.BytesIO(response.data))


def _rows(archive, table):
    with archive.open(f'data/{table}.csv') as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, encoding='utf-8', newline='')))


def test_admin_gets_a_zip_with_their_school_data(world):  # noqa: F811
    app, ids = world
    response = _download(app, ids)
    assert response.status_code == 200
    assert response.mimetype == 'application/zip'
    assert 'attachment' in response.headers['Content-Disposition']
    assert response.headers['Cache-Control'] == 'no-store'
    archive = _zip(response)
    names = archive.namelist()
    assert 'README.txt' in names and 'data/pupils.csv' in names and 'data/users.csv' in names
    first_names = {row['first_name'] for row in _rows(archive, 'pupils')}
    assert {'Alice', 'Beth'} <= first_names


def test_backup_never_contains_another_schools_data(world):  # noqa: F811
    app, ids = world
    archive = _zip(_download(app, ids))
    assert 'Other' not in {row['first_name'] for row in _rows(archive, 'pupils')}
    usernames = {row['username'] for row in _rows(archive, 'users')}
    assert 'teacher-b' not in usernames and {'teacher-a', 'admin-a'} <= usernames
    assert [row['slug'] for row in _rows(archive, 'schools')] == ['school-a']
    assert {row['id'] for row in _rows(archive, 'school_classes')} == {str(ids['ca'])}


def test_backup_has_no_password_hashes(world):  # noqa: F811
    app, ids = world
    response = _download(app, ids)
    archive = _zip(response)
    assert 'password_hash' not in _rows(archive, 'users')[0]
    with app.app_context():
        hashes = [u.password_hash for u in User.query.all()]
    for name in archive.namelist():
        content = archive.read(name)
        assert not any(h.encode() in content for h in hashes if h)


def test_teachers_cannot_download_a_backup(world):  # noqa: F811
    app, ids = world
    assert _download(app, ids, who='teacher').status_code == 403


def test_backup_needs_post_and_login(world):  # noqa: F811
    app, ids = world
    client = app.test_client()
    assert client.post('/admin/backup/download').status_code in (302, 401)
    login(client, ids['admin'])
    assert client.get('/admin/backup/download').status_code == 405


def test_download_is_recorded_in_the_audit_log(world):  # noqa: F811
    app, ids = world
    _download(app, ids)
    with app.app_context():
        entry = AuditLog.query.filter_by(action='school_backup_downloaded').first()
        assert entry is not None and entry.school_id == ids['a']


def test_every_table_is_either_scoped_or_deliberately_skipped(world):  # noqa: F811
    """If a new table is added without a school link, this fails so it is not silently left out."""
    app, ids = world
    with app.app_context():
        assert unscoped_tables() == [], f'Backup cannot scope these tables to a school: {unscoped_tables()}'
        for table in db.metadata.sorted_tables:
            if table.name in NOT_SCHOOL_DATA:
                assert scoped_select(table, ids['a']) is None
            else:
                assert scoped_select(table, ids['a']) is not None


def test_id_columns_get_readable_names_next_to_them(world):  # noqa: F811
    app, ids = world
    archive = _zip(_download(app, ids))
    pupils = _rows(archive, 'pupils')
    assert {row['class_name'] for row in pupils} == {'Oak'}
    assert [row['teacher_username'] for row in _rows(archive, 'school_classes')] == ['teacher-a']
    # wherever a table has pupil_id, the pupil's name must be present beside it
    with_ids = 0
    for name in archive.namelist():
        if not name.startswith('data/'):
            continue
        with archive.open(name) as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding='utf-8', newline=''))
            headers = reader.fieldnames or []
            if 'pupil_id' in headers:
                with_ids += 1
                assert headers[headers.index('pupil_id') + 1] == 'pupil_name', name
    assert with_ids > 0


def test_pupil_names_resolve_correctly(world):  # noqa: F811
    app, ids = world
    archive = _zip(_download(app, ids))
    by_id = {row['id']: f"{row['first_name']} {row['last_name']}" for row in _rows(archive, 'pupils')}
    for name in archive.namelist():
        if not name.startswith('data/') or name == 'data/pupils.csv':
            continue
        for row in _rows(archive, name[len('data/'):-len('.csv')]):
            if row.get('pupil_id'):
                assert row['pupil_name'] == by_id[row['pupil_id']], name
