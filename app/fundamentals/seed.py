"""Explicit, idempotent seeding for Maths Fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.fundamentals import early_number_sense_seed, number_bonds_seed, place_value_seed
from app.models import FundamentalLevel, FundamentalQuestion, FundamentalStrand


SEED_DATASETS = (
    early_number_sense_seed,
    number_bonds_seed,
    place_value_seed,
)

# A transaction-scoped PostgreSQL advisory lock prevents concurrent operators
# from racing the upserts. Other databases still get a retry on unique-key races.
POSTGRES_SEED_LOCK_ID = 4_613_195_428_101


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class SeedSummary:
    strands: EntityCounts = field(default_factory=EntityCounts)
    levels: EntityCounts = field(default_factory=EntityCounts)
    questions: EntityCounts = field(default_factory=EntityCounts)


def _get(row, *names):
    for name in names:
        if name in row:
            return row[name]
    return None


def _apply_values(record, values: dict, counts: EntityCounts, *, created: bool) -> None:
    changed = created
    for attribute, value in values.items():
        if getattr(record, attribute, None) != value:
            setattr(record, attribute, value)
            changed = True
    if created:
        counts.created += 1
    elif changed:
        counts.updated += 1
    else:
        counts.unchanged += 1


def _acquire_seed_lock() -> None:
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:lock_id)'),
            {'lock_id': POSTGRES_SEED_LOCK_ID},
        )


def _seed_once() -> SeedSummary:
    summary = SeedSummary()
    _acquire_seed_lock()
    strand_by_code = {}
    for dataset in SEED_DATASETS:
        for row in dataset.STRANDS:
            code = str(_get(row, 'StrandID', 'code'))
            strand = strand_by_code.get(code) or FundamentalStrand.query.filter_by(code=code).first()
            created = strand is None
            if created:
                strand = FundamentalStrand(code=code)
                db.session.add(strand)
            _apply_values(
                strand,
                {
                    'name': _get(row, 'StrandName', 'name'),
                    'description': _get(row, 'Description', 'description'),
                },
                summary.strands,
                created=created,
            )
            strand_by_code[code] = strand
    db.session.flush()

    for dataset in SEED_DATASETS:
        for row in dataset.LEVELS:
            strand = strand_by_code[str(_get(row, 'StrandID', 'code'))]
            level_number = int(_get(row, 'Level', 'level_number'))
            level = FundamentalLevel.query.filter_by(strand_id=strand.id, level_number=level_number).first()
            created = level is None
            if created:
                level = FundamentalLevel(strand_id=strand.id, level_number=level_number)
                db.session.add(level)
            _apply_values(
                level,
                {
                    'skill': _get(row, 'Skill', 'skill'),
                    'expected_year': _get(row, 'ExpectedYear', 'expected_year'),
                    'pass_mark': int(_get(row, 'PassMark', 'pass_mark') or 70),
                    'diagnostic_intent': _get(row, 'DiagnosticIntent', 'SuccessCriteria', 'diagnostic_intent'),
                    'key_representations': _get(row, 'KeyRepresentations', 'key_representations'),
                    'mastery_emphasis': _get(row, 'MasteryEmphasis', 'mastery_emphasis'),
                },
                summary.levels,
                created=created,
            )

    for dataset in SEED_DATASETS:
        for row in dataset.QUESTIONS:
            strand = strand_by_code[str(_get(row, 'StrandID', 'code'))]
            question_code = str(_get(row, 'QuestionID', 'question_id'))
            question = FundamentalQuestion.query.filter_by(strand_id=strand.id, question_id=question_code).first()
            created = question is None
            if created:
                question = FundamentalQuestion(strand_id=strand.id, question_id=question_code)
                db.session.add(question)
            _apply_values(
                question,
                {
                    'level_number': int(_get(row, 'Level', 'level_number')),
                    'question_type': _get(row, 'QuestionType', 'question_type'),
                    'question_text': _get(row, 'Question', 'question_text'),
                    'answer': str(_get(row, 'Answer', 'answer')),
                    'skill': _get(row, 'Skill', 'skill'),
                    'representation_type': _get(row, 'RepresentationType', 'representation_type'),
                    'mastery_focus': _get(row, 'MasteryFocus', 'mastery_focus'),
                    'rendering_notes': _get(row, 'RenderingSuggestion', 'rendering_notes'),
                    'visual_data': _get(row, 'VisualData', 'visual_data'),
                },
                summary.questions,
                created=created,
            )

    db.session.commit()
    return summary


def seed_fundamentals(*, retries: int = 1) -> SeedSummary:
    """Create/update the question bank by stable IDs without deleting data."""

    for attempt_number in range(retries + 1):
        try:
            return _seed_once()
        except IntegrityError:
            db.session.rollback()
            if attempt_number >= retries:
                raise
        except Exception:
            db.session.rollback()
            raise
    raise RuntimeError('Maths Fundamentals seeding did not complete.')
