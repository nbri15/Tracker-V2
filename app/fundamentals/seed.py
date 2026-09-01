"""Idempotent seeding for Maths Fundamentals."""

from app.extensions import db
from app.fundamentals import early_number_sense_seed, number_bonds_seed
from app.models import FundamentalLevel, FundamentalQuestion, FundamentalStrand


SEED_DATASETS = (
    early_number_sense_seed,
    number_bonds_seed,
)


def _get(row, *names):
    for name in names:
        if name in row:
            return row[name]
    return None


def seed_fundamentals() -> None:
    """Create or update all Maths Fundamentals seed records without duplication."""
    strand_by_code = {}
    for dataset in SEED_DATASETS:
        for row in dataset.STRANDS:
            code = _get(row, 'StrandID', 'code')
            strand = strand_by_code.get(code) or FundamentalStrand.query.filter_by(code=code).first()
            if not strand:
                strand = FundamentalStrand(code=code)
                db.session.add(strand)
            strand.name = _get(row, 'StrandName', 'name')
            strand.description = _get(row, 'Description', 'description')
            strand_by_code[code] = strand
    db.session.flush()

    for dataset in SEED_DATASETS:
        for row in dataset.LEVELS:
            strand_code = _get(row, 'StrandID', 'code')
            strand = strand_by_code.get(strand_code) or FundamentalStrand.query.filter_by(code=strand_code).first()
            level_number = int(_get(row, 'Level', 'level_number'))
            level = FundamentalLevel.query.filter_by(strand_id=strand.id, level_number=level_number).first()
            if not level:
                level = FundamentalLevel(strand_id=strand.id, level_number=level_number)
                db.session.add(level)
            level.skill = _get(row, 'Skill', 'skill')
            level.expected_year = _get(row, 'ExpectedYear', 'expected_year')
            level.pass_mark = int(_get(row, 'PassMark', 'pass_mark') or 70)

    for dataset in SEED_DATASETS:
        for row in dataset.QUESTIONS:
            strand_code = _get(row, 'StrandID', 'code')
            strand = strand_by_code.get(strand_code) or FundamentalStrand.query.filter_by(code=strand_code).first()
            question_code = _get(row, 'QuestionID', 'question_id')
            question = FundamentalQuestion.query.filter_by(strand_id=strand.id, question_id=question_code).first()
            if not question:
                question = FundamentalQuestion(strand_id=strand.id, question_id=question_code)
                db.session.add(question)
            question.level_number = int(_get(row, 'Level', 'level_number'))
            question.question_type = _get(row, 'QuestionType', 'question_type')
            question.question_text = _get(row, 'Question', 'question_text')
            question.answer = str(_get(row, 'Answer', 'answer'))

    db.session.commit()
