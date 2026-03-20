"""GAP / QLA service helpers."""

from __future__ import annotations

from collections import defaultdict

from app.extensions import db
from app.models import GapQuestion, GapScore, GapTemplate, SubjectResult
from .assessments import AssessmentValidationError, get_subject_setting

GAP_PAPERS = ('paper_1', 'paper_2')


def build_gap_paper_tabs(subject: str, setting) -> list[dict]:
    paper_labels = {
        'paper_1': setting.paper_1_name or 'Paper 1',
        'paper_2': setting.paper_2_name or 'Paper 2',
    }
    supports_two_papers = subject in {'maths', 'reading', 'spag'}
    papers = ['paper_1', 'paper_2'] if supports_two_papers else ['paper_1']
    return [{'key': paper, 'label': paper_labels[paper]} for paper in papers]


def get_or_create_gap_template(year_group: int, subject: str, term: str, academic_year: str) -> GapTemplate:
    template = GapTemplate.query.filter_by(year_group=year_group, subject=subject, term=term, academic_year=academic_year).first()
    if template:
        return template
    template = GapTemplate(year_group=year_group, subject=subject, term=term, academic_year=academic_year)
    db.session.add(template)
    db.session.flush()
    return template


def parse_question_columns(form, template: GapTemplate, *, selected_paper: str = 'paper_1') -> list[GapQuestion]:
    questions: list[GapQuestion] = []
    question_ids = form.getlist('question_id[]')
    labels = form.getlist('question_label[]')
    types = form.getlist('question_type[]')
    max_scores = form.getlist('question_max[]')
    display_orders = form.getlist('question_display_order[]')
    papers = form.getlist('question_paper[]')

    if selected_paper not in GAP_PAPERS:
        selected_paper = 'paper_1'

    for index, label in enumerate(labels):
        question_id = (question_ids[index] if index < len(question_ids) else '').strip()
        label = label.strip()
        question_type = (types[index] if index < len(types) else '').strip() or None
        max_raw = (max_scores[index] if index < len(max_scores) else '').strip()
        display_order_raw = (display_orders[index] if index < len(display_orders) else '').strip()
        paper = (papers[index] if index < len(papers) else selected_paper).strip() or selected_paper
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
        try:
            display_order = int(display_order_raw or str(index + 1))
        except ValueError as exc:
            raise AssessmentValidationError(f'Question {label}: display order must be a whole number.') from exc
        if paper not in GAP_PAPERS:
            raise AssessmentValidationError(f'Question {label}: choose a valid paper.')
        question = GapQuestion.query.get(int(question_id)) if question_id else GapQuestion(template_id=template.id)
        question.question_label = label
        question.question_type = question_type
        question.max_score = max_score
        question.paper = paper
        question.display_order = display_order
        question.template = template
        db.session.add(question)
        questions.append(question)

    if not questions:
        raise AssessmentValidationError('Add at least one GAP question column before saving.')

    existing_ids = {question.id for question in questions if question.id}
    for old_question in list(template.questions):
        if old_question.paper == selected_paper and old_question.id not in existing_ids:
            db.session.delete(old_question)
    db.session.flush()
    return sorted(questions, key=lambda question: (question.display_order, question.id or 0))


def save_gap_scores(pupils, template: GapTemplate, questions: list[GapQuestion], form) -> dict:
    warnings = []
    score_lookup = {(score.pupil_id, score.question_id): score for question in questions for score in question.scores}

    for pupil in pupils:
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

    db.session.flush()
    pupil_totals = _build_template_pupil_totals(pupils, template)
    warnings.extend(sync_gap_totals_to_subject_results(pupils, list(template.questions), pupil_totals))
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


def _build_template_pupil_totals(pupils, template: GapTemplate) -> dict[int, float | None]:
    question_ids = [question.id for question in template.questions]
    scores = GapScore.query.filter(GapScore.question_id.in_(question_ids)).all() if question_ids else []
    totals = {pupil.id: 0.0 for pupil in pupils}
    has_scores = {pupil.id: False for pupil in pupils}
    valid_pupil_ids = {pupil.id for pupil in pupils}
    for score in scores:
        if score.pupil_id not in valid_pupil_ids or score.score is None:
            continue
        totals[score.pupil_id] += score.score
        has_scores[score.pupil_id] = True
    return {pupil.id: totals[pupil.id] if has_scores[pupil.id] else None for pupil in pupils}


def build_gap_page_context(pupils, template: GapTemplate, *, subject: str, selected_paper: str, setting) -> dict:
    all_questions = list(template.questions)
    question_ids = [question.id for question in all_questions]
    scores = GapScore.query.filter(GapScore.question_id.in_(question_ids)).all() if question_ids else []
    score_map = {(score.pupil_id, score.question_id): score.score for score in scores}
    selected_questions = [question for question in all_questions if (question.paper or 'paper_1') == selected_paper]
    paper_tabs = build_gap_paper_tabs(subject, setting)
    valid_papers = {paper['key'] for paper in paper_tabs}
    if selected_paper not in valid_papers:
        selected_paper = paper_tabs[0]['key']
        selected_questions = [question for question in all_questions if (question.paper or 'paper_1') == selected_paper]
    paper_summaries = []

    for paper in paper_tabs:
        paper_questions = [question for question in all_questions if (question.paper or 'paper_1') == paper['key']]
        max_total = sum(question.max_score or 0 for question in paper_questions)
        answered_cells = 0
        for pupil in pupils:
            for question in paper_questions:
                if score_map.get((pupil.id, question.id)) is not None:
                    answered_cells += 1
        paper_summaries.append(
            {
                'key': paper['key'],
                'label': paper['label'],
                'question_count': len(paper_questions),
                'max_total': max_total,
                'answered_cells': answered_cells,
            }
        )

    rows = []
    question_totals = defaultdict(float)
    question_counts = defaultdict(int)
    topic_totals = defaultdict(float)
    topic_counts = defaultdict(int)
    combined_totals = _build_template_pupil_totals(pupils, template)
    current_paper_row_totals: list[float] = []
    combined_row_totals: list[float] = []

    for pupil in pupils:
        total = 0.0
        row_scores = []
        has_any = False
        for question in selected_questions:
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
        current_total = total if has_any else None
        combined_total = combined_totals.get(pupil.id)
        if current_total is not None:
            current_paper_row_totals.append(current_total)
        if combined_total is not None:
            combined_row_totals.append(combined_total)
        rows.append({'pupil': pupil, 'scores': row_scores, 'total': current_total, 'combined_total': combined_total})

    question_averages = []
    for question in selected_questions:
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
        'questions': selected_questions,
        'all_questions': all_questions,
        'rows': rows,
        'max_total': sum(question.max_score or 0 for question in selected_questions),
        'combined_max_total': sum(question.max_score or 0 for question in all_questions),
        'question_averages': question_averages,
        'lowest_questions': lowest_questions,
        'weakest_topics': weakest_topics,
        'paper_tabs': paper_tabs,
        'paper_summaries': paper_summaries,
        'selected_paper': selected_paper,
        'selected_paper_label': next((paper['label'] for paper in paper_tabs if paper['key'] == selected_paper), 'Paper 1'),
        'current_paper_average_total': round(sum(current_paper_row_totals) / len(current_paper_row_totals), 1) if current_paper_row_totals else None,
        'combined_average_total': round(sum(combined_row_totals) / len(combined_row_totals), 1) if combined_row_totals else None,
    }
