"""GAP / QLA service helpers."""

from __future__ import annotations

from collections import defaultdict

from app.extensions import db
from app.models import GapQuestion, GapScore, GapTemplate, SubjectResult
from .assessments import AssessmentValidationError, get_subject_setting


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


def save_gap_scores(pupils, questions: list[GapQuestion], form) -> dict:
    warnings = []
    score_lookup = {(score.pupil_id, score.question_id): score for question in questions for score in question.scores}
    pupil_totals = {}

    for pupil in pupils:
        total = 0.0
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
            row.score = score_value
            db.session.add(row)
            total += score_value
            has_any_value = True
        pupil_totals[pupil.id] = total if has_any_value else None

    warnings.extend(sync_gap_totals_to_subject_results(pupils, questions, pupil_totals))
    return {'warnings': warnings, 'pupil_totals': pupil_totals}


def sync_gap_totals_to_subject_results(pupils, questions: list[GapQuestion], pupil_totals: dict[int, float | None]) -> list[str]:
    warnings: list[str] = []
    if not questions:
        return warnings
    template = questions[0].template
    template_max_total = sum(question.max_score or 0 for question in questions)
    setting = get_subject_setting(template.year_group, template.subject, template.term)
    combined_max = template_max_total or setting.combined_max

    existing_results = {
        result.pupil_id: result
        for result in SubjectResult.query.filter_by(subject=template.subject, term=template.term, academic_year=template.academic_year).filter(SubjectResult.pupil_id.in_([pupil.id for pupil in pupils])).all()
    }

    for pupil in pupils:
        total = pupil_totals.get(pupil.id)
        result = existing_results.get(pupil.id)
        if total is None:
            continue
        rounded_total = int(total) if float(total).is_integer() else total
        if result is None:
            result = SubjectResult(pupil_id=pupil.id, academic_year=template.academic_year, term=template.term, subject=template.subject)
            result.source = 'gap'
            result.combined_score = rounded_total
            result.combined_percent = SubjectResult.calculate_percent(rounded_total, combined_max)
            result.band_label = SubjectResult.calculate_band_label(result.combined_percent, setting.below_are_threshold_percent, setting.exceeding_threshold_percent)
            db.session.add(result)
            continue
        if result.source in {'manual', 'csv'} and result.combined_score is not None and result.combined_score != rounded_total:
            warnings.append(f'{pupil.full_name}: GAP total {rounded_total} differs from saved {result.source} score {result.combined_score}.')
            continue
        if result.combined_score is None:
            result.combined_score = rounded_total
            result.combined_percent = SubjectResult.calculate_percent(rounded_total, combined_max)
            result.band_label = SubjectResult.calculate_band_label(result.combined_percent, setting.below_are_threshold_percent, setting.exceeding_threshold_percent)
            result.source = 'gap'
            db.session.add(result)
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
