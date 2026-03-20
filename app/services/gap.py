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
    labels = form.getlist('question_label[]')
    types = form.getlist('question_type[]')
    max_scores = form.getlist('question_max[]')

    for index, label in enumerate(labels):
        question_id = (question_ids[index] if index < len(question_ids) else '').strip()
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
    topic_totals = defaultdict(float)
    topic_counts = defaultdict(int)

    for pupil in pupils:
        total = 0.0
        row_scores = []
        has_any = False
        for question in questions:
            score = score_map.get((pupil.id, question.id))
            row_scores.append(score)
            if score is not None:
                total += score
                has_any = True
                question_totals[question.id] += score
                question_counts[question.id] += 1
                if question.question_type:
                    topic_totals[question.question_type] += score / question.max_score if question.max_score else 0
                    topic_counts[question.question_type] += 1
        rows.append({'pupil': pupil, 'scores': row_scores, 'total': total if has_any else None})

    question_averages = []
    for question in questions:
        avg = question_totals[question.id] / question_counts[question.id] if question_counts[question.id] else None
        pct = ((avg / question.max_score) * 100) if avg is not None and question.max_score else None
        question_averages.append({'question': question, 'average': round(avg, 2) if avg is not None else None, 'percent': round(pct, 1) if pct is not None else None})

    lowest_questions = sorted(
        [item for item in question_averages if item['percent'] is not None],
        key=lambda item: item['percent'],
    )[:5]
    weakest_topics = sorted(
        [
            {'topic': topic, 'average_percent': round((topic_totals[topic] / topic_counts[topic]) * 100, 1)}
            for topic in topic_totals
            if topic_counts[topic]
        ],
        key=lambda item: item['average_percent'],
    )[:5]

    return {
        'template': template,
        'questions': questions,
        'rows': rows,
        'max_total': sum(question.max_score or 0 for question in questions),
        'question_averages': question_averages,
        'lowest_questions': lowest_questions,
        'weakest_topics': weakest_topics,
        'blank_question_slots': range(4),
    }
