"""Command-line administration for Maths Fundamentals."""

import click
from flask.cli import with_appcontext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.fundamentals import seed as seed_service


FUNDAMENTALS_TABLES = (
    'fundamental_strands',
    'fundamental_levels',
    'fundamental_questions',
    'fundamental_sessions',
    'fundamental_pupil_attempts',
    'fundamental_responses',
)


@click.group('fundamentals')
def fundamentals_cli() -> None:
    """Manage the Maths Fundamentals add-on."""


@fundamentals_cli.command('seed')
@with_appcontext
def seed_command() -> None:
    """Create or refresh the Maths Fundamentals question bank."""

    inspector = inspect(db.engine)
    missing = [table for table in FUNDAMENTALS_TABLES if not inspector.has_table(table)]
    if missing:
        raise click.ClickException(
            'Maths Fundamentals schema is not current. Run "flask db upgrade" first. '
            f'Missing: {", ".join(missing)}.'
        )

    try:
        summary = seed_service.seed_fundamentals()
    except IntegrityError as error:
        db.session.rollback()
        raise click.ClickException(
            'The question bank could not be seeded because of a concurrent or conflicting write. '
            'No seed transaction was committed; rerun the command.'
        ) from error

    for label, counts in (
        ('Strands', summary.strands),
        ('Levels', summary.levels),
        ('Questions', summary.questions),
    ):
        click.echo(
            f'{label}: {counts.created} created, {counts.updated} updated, '
            f'{counts.unchanged} unchanged.'
        )
