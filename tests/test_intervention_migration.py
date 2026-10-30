"""Run the actual additive migration against existing fictional records."""
import importlib.util
import os
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration():
    path=Path(__file__).resolve().parents[1]/'migrations/versions/20261030_01_intervention_programmes.py'
    spec=importlib.util.spec_from_file_location('intervention_programmes_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('dialect',['sqlite','postgresql'])
def test_programme_migration_keeps_existing_records(dialect):
    url='sqlite://'
    if dialect=='postgresql':
        url=os.environ.get('CC_TEST_POSTGRES_URL')
        if not url: pytest.skip('Disposable PostgreSQL service is enabled in CI')
        parsed=sa.engine.make_url(url)
        assert parsed.host in {'127.0.0.1','localhost'}
        assert parsed.database=='class_compass_intervention_migration_test'
    engine=sa.create_engine(url)
    with engine.begin() as connection:
        if dialect=='postgresql':
            connection.execute(sa.text('CREATE SCHEMA intervention_migration_test'))
            connection.execute(sa.text('SET LOCAL search_path TO intervention_migration_test'))
        connection.execute(sa.text('CREATE TABLE schools (id INTEGER PRIMARY KEY)'))
        connection.execute(sa.text('CREATE TABLE interventions (id INTEGER PRIMARY KEY, is_active BOOLEAN NOT NULL, note TEXT)'))
        connection.execute(sa.text('INSERT INTO schools (id) VALUES (1), (2)'))
        connection.execute(sa.text('INSERT INTO interventions (id,is_active,note) VALUES (:id,:active,:note)'),
                           [{'id':1,'active':True,'note':'Fictional active plan'}, {'id':2,'active':False,'note':'Fictional closed history'}])
        context=MigrationContext.configure(connection)
        with Operations.context(context): migration().upgrade()
        rows=connection.execute(sa.text('SELECT id,is_active,note,closed_by_teacher FROM interventions ORDER BY id')).all()
        assert rows==[(1,True,'Fictional active plan',False),(2,False,'Fictional closed history',True)]
        connection.execute(sa.text("INSERT INTO intervention_programmes (id,school_id,name,name_key,subject) VALUES (1,1,'Booster','booster','maths')"))
        connection.execute(sa.text('INSERT INTO intervention_programme_assignments (intervention_id,programme_id,school_id) VALUES (1,1,1)'))
        assert connection.execute(sa.text('SELECT is_active FROM intervention_programmes')).scalar() in (True,1)
        inspector=sa.inspect(connection)
        assert len(inspector.get_pk_constraint('intervention_programme_assignments')['constrained_columns'])==2
        if dialect=='postgresql': connection.execute(sa.text('DROP SCHEMA intervention_migration_test CASCADE'))
    engine.dispose()
