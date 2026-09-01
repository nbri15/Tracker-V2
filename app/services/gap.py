"""GAP / QLA service helpers."""

from __future__ import annotations

from collections import defaultdict
import logging

from app.extensions import db
from app.models import GapQuestion, GapScore, GapTemplate, SubjectResult
from .assessments import (
    AssessmentValidationError,
    compute_subject_result_values,
    get_subject_setting,
    resolve_subject_band_label,
)

logger = logging.getLogger(__name__)


def get_or_create_gap_template(year_group: int, subject: str, term: str, academic_year: str) -> GapTemplate:
    template = GapTemplate.query.filter_by(year_group=year_group, subject=subject, term=term, academic_year=academic_year).first()
    if template:
        return template
    template = GapTemplate(year_group=year_group, subject=subject, term=term, academic_year=academic_year)
    db.session.add(template)
    db.session.flush()
    return template


def parse_question_columns(form, template: GapTemplate) -> list[GapQuestion]:
    questions: list[GapQuestion] = []
    question_ids = form.getlist('question_id[]')
    paper_keys = form.getlist('question_paper[]')
    labels = form.getlist('question_label[]')
    types = form.getlist('question_type[]')
    max_scores = form.getlist('question_max[]')

    for index, label in enumerate(labels):
        question_id = (question_ids[index] if index < len(question_ids) else '').strip()
        paper_key = (paper_keys[index] if index < len(paper_keys) else 'paper_1').strip() or 'paper_1'
        label = label.strip()
        question_type = (types[index] if index < len(types) else '').strip() or None
        max_raw = (max_scores[index] if index < len(max_scores) else '').strip()
        if not label and not max_raw and not question_type:
            continue
        if not label:
            raise AssessmentValidationError('Every GAP question column needs a label.')
        try:
            max_score = int(max_raw or '0')
        except ValueError as exc:
            raise AssessmentValidationError(f'Question {label}: max score must be a whole number.') from exc
        if max_score < 0:
            raise AssessmentValidationError(f'Question {label}: max score cannot be negative.')
        question = GapQuestion.query.get(int(question_id)) if question_id else GapQuestion(template_id=template.id)
        question.school_id = template.school_id
        question.paper_key = paper_key
        question.question_label = label
        question.question_type = question_type
        question.max_score = max_score
        question.display_order = len(questions)
        question.template = template
        db.session.add(question)
        questions.append(question)

    if not questions:
        raise AssessmentValidationError('Add at least one GAP question column before saving.')

    existing_ids = {question.id for question in questions if question.id}
    for old_question in list(template.questions):
        if old_question.id not in existing_ids:
            db.session.delete(old_question)
    db.session.flush()
    return questions


def save_gap_scores(pupils, questions: list[GapQuestion], form, *, school_id: int | None = None, assessment_year_group: int | None = None) -> dict:
    warnings = []
    score_lookup = {(score.pupil_id, score.question_id): score for question in questions for score in question.scores}
    pupil_totals = {}
    pupil_paper_totals = {}

    for pupil in pupils:
        total = 0.0
        paper_totals = defaultdict(float)
        paper_has_any = defaultdict(bool)
        has_any_value = False
        for question in questions:
            field_name = f'score_{pupil.id}_{question.id}'
            raw_value = form.get(field_name, '').strip()
            existing = score_lookup.get((pupil.id, question.id))
            if raw_value == '':
                if existing:
                    db.session.delete(existing)
                continue
            try:
                score_value = float(raw_value)
            except ValueError as exc:
                raise AssessmentValidationError(f'{pupil.full_name} question {question.question_label}: score must be numeric.') from exc
            if score_value < 0:
                raise AssessmentValidationError(f'{pupil.full_name} question {question.question_label}: score cannot be negative.')
            if question.max_score is not None and score_value > question.max_score:
                raise AssessmentValidationError(f'{pupil.full_name} question {question.question_label}: score cannot exceed {question.max_score}.')
            row = existing or GapScore(pupil_id=pupil.id, question_id=question.id)
            row.school_id = school_id if school_id is not None else question.school_id
            row.score = score_value
            db.session.add(row)
            total += score_value
            paper_key = question.paper_key or 'paper_1'
            paper_totals[paper_key] += score_value
            paper_has_any[paper_key] = True
            has_any_value = True
        pupil_totals[pupil.id] = total if has_any_value else None
        pupil_paper_totals[pupil.id] = {paper_key: paper_totals[paper_key] for paper_key in paper_has_any}

    warnings.extend(sync_gap_totals_to_subject_results(pupils, questions, pupil_totals, pupil_paper_totals, school_id=school_id, assessment_year_group=assessment_year_group))
    return {'warnings': warnings, 'pupil_totals': pupil_totals, 'pupil_paper_totals': pupil_paper_totals}


def build_gap_totals_from_saved_scores(pupils, questions: list[GapQuestion]) -> tuple[dict[int, float | None], dict[int, dict[str, float]]]:
    question_ids = [question.id for question in questions if question.id]
    score_rows = GapScore.query.filter(GapScore.question_id.in_(question_ids)).all() if question_ids else []
    question_by_id = {question.id: question for question in questions}
    pupil_ids = {pupil.id for pupil in pupils}
    pupil_totals: dict[int, float | None] = {pupil.id: None for pupil in pupils}
    pupil_paper_totals: dict[int, dict[str, float]] = {pupil.id: {} for pupil in pupils}

    for score_row in score_rows:
        if score_row.pupil_id not in pupil_ids or score_row.score is None:
            continue
        question = question_by_id.get(score_row.question_id)
        if question is None:
            continue
        paper_key = question.paper_key or 'paper_1'
        pupil_totals[score_row.pupil_id] = (pupil_totals[score_row.pupil_id] or 0) + score_row.score
        pupil_paper_totals[score_row.pupil_id][paper_key] = pupil_paper_totals[score_row.pupil_id].get(paper_key, 0) + score_row.score

    return pupil_totals, pupil_paper_totals


def _normalise_score(total: float) -> int | float:
    return int(total) if float(total).is_integer() else total


def sync_gap_totals_to_subject_results(
    pupils,
    questions: list[GapQuestion],
    pupil_totals: dict[int, float | None] | None = None,
    pupil_paper_totals: dict[int, dict[str, float]] | None = None,
    *,
    school_id: int | None = None,
    assessment_year_group: int | None = None,
) -> list[str]:
    warnings: list[str] = []
    if not questions:
        return warnings
    if pupil_totals is None or pupil_paper_totals is None:
        pupil_totals, pupil_paper_totals = build_gap_totals_from_saved_scores(pupils, questions)

    template = questions[0].template
    setting = get_subject_setting(template.year_group, template.subject, template.term)
    effective_school_id = school_id if school_id is not None else template.school_id
    pupil_ids = [pupil.id for pupil in pupils]

    existing_results = {
        result.pupil_id: result
        for result in SubjectResult.query.filter_by(
            subject=template.subject,
            term=template.term,
            academic_year=template.academic_year,
        ).filter(SubjectResult.pupil_id.in_(pupil_ids)).all()
    }

    updated = 0
    total_scores_synced = 0
    for pupil in pupils:
        per_paper = pupil_paper_totals.get(pupil.id, {})
        if not per_paper:
            continue
        result = existing_results.get(pupil.id)
        if result is None:
            result = SubjectResult(
                school_id=effective_school_id,
                pupil_id=pupil.id,
                academic_year=template.academic_year,
                term=template.term,
                subject=template.subject,
            )
        result.school_id = effective_school_id
        result.assessment_year_group = assessment_year_group if assessment_year_group is not None else template.year_group
        if 'paper_1' in per_paper:
            result.paper_1_score = _normalise_score(per_paper['paper_1'])
            total_scores_synced += 1
        if 'paper_2' in per_paper:
            result.paper_2_score = _normalise_score(per_paper['paper_2'])
            total_scores_synced += 1
        computed = compute_subject_result_values(setting, result.paper_1_score, result.paper_2_score, validate_scores=False)
        result.combined_score = computed['combined_score']
        result.combined_percent = computed['combined_percent']
        result.band_label = resolve_subject_band_label(
            percent=computed['combined_percent'],
            setting=setting,
            pupil_year_group=template.year_group,
            assessment_year_group=result.assessment_year_group,
        )
        result.source = 'gap'
        db.session.add(result)
        updated += 1

    logger.info(
        'QLA/GAP totals synced to subject results: assessment_id=%s subject=%s paper=%s pupils_updated=%s total_scores_synced=%s',
        template.id,
        template.subject,
        template.paper_name or 'all',
        updated,
        total_scores_synced,
    )
    return warnings

def build_gap_page_context(pupils, template: GapTemplate) -> dict:
    questions = list(template.questions)
    question_ids = [question.id for question in questions]
    scores = GapScore.query.filter(GapScore.question_id.in_(question_ids)).all() if question_ids else []
    score_map = {(score.pupil_id, score.question_id): score.score for score in scores}

    rows = []
    question_totals = defaultdict(float)
    question_counts = defaultdict(int)

    for pupil in pupils:
        total = 0.0
        row_scores = {}
        paper_totals = defaultdict(float)
        paper_has_any = defaultdict(bool)
        has_any = False
        for question in questions:
            score = score_map.get((pupil.id, question.id))
            row_scores[question.id] = score
            if score is not None:
                total += score
                has_any = True
                paper_totals[question.paper_key or 'paper_1'] += score
                paper_has_any[question.paper_key or 'paper_1'] = True
                question_totals[question.id] += score
                question_counts[question.id] += 1
        rows.append(
            {
                'pupil': pupil,
                'scores': row_scores,
                'total': total if has_any else None,
                'paper_totals': {
                    paper_key: (value if paper_has_any.get(paper_key) else None)
                    for paper_key, value in paper_totals.items()
                },
            }
        )

    question_averages_by_id = {}
    for question in questions:
        avg = question_totals[question.id] / question_counts[question.id] if question_counts[question.id] else None
        pct = ((avg / question.max_score) * 100) if avg is not None and question.max_score else None
        question_averages_by_id[question.id] = {
            'question': question,
            'average': round(avg, 2) if avg is not None else None,
            'percent': round(pct, 1) if pct is not None else None,
        }

    paper_order = []
    seen_papers = set()
    for question in questions:
        paper_key = question.paper_key or 'paper_1'
        if paper_key not in seen_papers:
            paper_order.append(paper_key)
            seen_papers.add(paper_key)

    papers = []
    for paper_key in paper_order:
        paper_questions = [question for question in questions if (question.paper_key or 'paper_1') == paper_key]
        papers.append(
            {
                'key': paper_key,
                'questions': paper_questions,
                'max_total': sum(question.max_score or 0 for question in paper_questions),
                'question_averages': [question_averages_by_id[question.id] for question in paper_questions],
            }
        )

    return {
        'template': template,
        'questions': questions,
        'papers': papers,
        'rows': rows,
        'max_total': sum(question.max_score or 0 for question in questions),
        'question_averages': [question_averages_by_id[question.id] for question in questions],
    }
