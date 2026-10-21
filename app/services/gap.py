"""GAP / QLA service helpers."""

from __future__ import annotations

from collections import defaultdict
import logging
import math
from app.utils import current_school_id

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
    template = GapTemplate.query.filter_by(school_id=current_school_id(), year_group=year_group, subject=subject, term=term, academic_year=academic_year).first()
    if template:
        return template
    template = GapTemplate(school_id=current_school_id(), year_group=year_group, subject=subject, term=term, academic_year=academic_year)
    db.session.add(template)
    db.session.flush()
    return template


def parse_question_columns(form, template: GapTemplate) -> list[GapQuestion]:
    """Edit definitions in place; never discard marks while changing a template."""
    from flask import abort
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.can_manage_school:
        abort(403)
    if template.school_id != current_school_id():
        abort(403)
    original = list(template.questions)
    by_id = {question.id: question for question in original}
    ids = form.getlist('question_id[]')
    papers = form.getlist('question_paper[]')
    labels = form.getlist('question_label[]')
    topics = form.getlist('question_type[]')
    maxima = form.getlist('question_max[]')
    if not (len(ids) == len(papers) == len(labels) == len(topics) == len(maxima)):
        raise AssessmentValidationError('Incomplete question columns; reload the template and try again.')
    proposed = []
    retained = set()
    for raw_id, paper, label, topic, raw_max in zip(ids, papers, labels, topics, maxima):
        label, topic, raw_max = label.strip(), topic.strip(), raw_max.strip()
        if not raw_id.strip() and not label and not raw_max and not topic:
            continue
        try:
            question_id = int(raw_id) if raw_id.strip() else None
            maximum = int(raw_max)
        except (ValueError, TypeError) as exc:
            raise AssessmentValidationError('Question IDs and maximum marks must be whole numbers.') from exc
        if not label or len(label) > 20 or len(topic) > 120 or maximum < 0 or paper not in {'paper_1', 'paper_2'}:
            raise AssessmentValidationError('Enter a question label (up to 20 characters), valid paper, topic (up to 120 characters) and non-negative maximum.')
        question = by_id.get(question_id) if question_id is not None else None
        if question_id is not None:
            if question is None or question_id in retained:
                raise AssessmentValidationError('Unknown or repeated question ID; reload this template.')
            retained.add(question_id)
            if question.scores and paper != question.paper_key:
                raise AssessmentValidationError(f'Question {question.question_label} has pupil marks and cannot be moved to another paper.')
            if any(score.score is not None and score.score > maximum for score in question.scores):
                raise AssessmentValidationError(f'Question {question.question_label}: maximum cannot be below an existing pupil mark.')
        proposed.append((question, paper, label, topic, maximum))
    if not proposed:
        raise AssessmentValidationError('Add at least one GAP question column before saving.')
    removed = [question for question in original if question.id not in retained]
    if any(question.scores for question in removed):
        raise AssessmentValidationError('Questions with pupil marks cannot be removed. Keep their IDs and existing marks.')
    questions = []
    for order, (question, paper, label, topic, maximum) in enumerate(proposed):
        question = question or GapQuestion(template=template)
        question.school_id = template.school_id
        question.paper_key, question.question_label = paper, label
        question.question_type, question.max_score = topic or None, maximum
        question.display_order = order
        db.session.add(question)
        questions.append(question)
    for question in removed:
        db.session.delete(question)
    db.session.flush()
    return questions


def validate_score_columns(form, questions):
    """Reject stale/forged columns without permitting score entry to edit definitions."""
    if 'question_id[]' not in form:
        return
    expected = {str(question.id): question for question in questions}
    ids = form.getlist('question_id[]')
    if len(ids) != len(expected) or set(ids) != set(expected):
        raise AssessmentValidationError('The GAP template changed; reload before saving scores.')
    fields = {'question_label[]': 'question_label', 'question_paper[]': 'paper_key',
              'question_type[]': 'question_type', 'question_max[]': 'max_score'}
    for field, attribute in fields.items():
        values = form.getlist(field)
        if len(values) != len(ids) or any(value != str(getattr(expected[key], attribute) or (0 if attribute == 'max_score' else '')) for key, value in zip(ids, values)):
            raise AssessmentValidationError('Only administrators can change GAP question definitions. Reload before saving scores.')


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
            if field_name not in form:
                continue  # An omitted cell is not an instruction to erase a saved mark.
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
            if not math.isfinite(score_value):
                raise AssessmentValidationError(f'{pupil.full_name}: enter a finite score.')
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

    db.session.flush()
    pupil_totals, pupil_paper_totals = build_gap_totals_from_saved_scores(pupils, questions)
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
    setting = get_subject_setting(template.year_group, template.subject, template.term, template.academic_year, school_id=template.school_id)
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

    from .assessment_reliability import apply_result, setting_for_result
    saved_scores = {(score.pupil_id, score.question_id): score.score for score in GapScore.query.filter(GapScore.question_id.in_([question.id for question in questions])).all()}
    updated = 0
    total_scores_synced = 0
    for pupil in pupils:
        per_paper = dict(pupil_paper_totals.get(pupil.id, {}))
        for paper in list(per_paper):
            paper_questions = [question for question in questions if (question.paper_key or 'paper_1') == paper]
            if any(saved_scores.get((pupil.id, question.id)) is None for question in paper_questions):
                per_paper.pop(paper)
                warnings.append(f'{pupil.full_name}: {paper} is incomplete; its assessment score was kept.')
        if not per_paper:
            continue
        if any(total is not None and int(total) != total for total in per_paper.values()):
            warnings.append(f'{pupil.full_name}: fractional GAP total kept in GAP; assessment paper scores require whole marks.')
            continue
        for paper in list(per_paper):
            maximum = setting.paper_1_max if paper == 'paper_1' else setting.paper_2_max
            question_maximum = sum(question.max_score or 0 for question in questions if (question.paper_key or 'paper_1') == paper)
            if question_maximum != maximum:
                warnings.append(f'{pupil.full_name}: {paper} questions total {question_maximum} marks, but assessment maximum is {maximum}; assessment score kept.')
                per_paper.pop(paper)
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
        result.pupil = pupil
        effective_setting = setting_for_result(result, setting)
        apply_result(result, effective_setting, result.paper_1_score, result.paper_2_score,
            cohort=template.year_group, assessment_year_group=result.assessment_year_group, source='gap')
        updated += 1

    if updated:
        from app.utils import log_audit_event
        log_audit_event('assessment_bulk_results_changed', 'gap_template', template.id, school_id=effective_school_id,
            details=f'GAP synced {updated} {template.subject} results; {template.academic_year} {template.term}')
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
