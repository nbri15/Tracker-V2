"""Place Value question-bank, presentation and answer-handling coverage."""

from types import SimpleNamespace
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.fundamentals import place_value_seed
from app.fundamentals.presentation import answers_match, question_presentation
from app.fundamentals.routes import _default_start_level


def _row(question_id):
    return next(row for row in place_value_seed.QUESTIONS if row['QuestionID'] == question_id)


def _question(question_id):
    row = _row(question_id)
    return SimpleNamespace(
        question_text=row['Question'],
        answer=row['Answer'],
        visual_data=row['VisualData'],
        rendering_notes=row['RenderingSuggestion'],
        representation_type=row['RepresentationType'],
        mastery_focus=row['MasteryFocus'],
    )


def test_authoritative_place_value_dataset_counts_and_ids():
    assert place_value_seed.SOURCE['question_count'] == 600
    assert len(place_value_seed.LEVELS) == 20
    assert len(place_value_seed.QUESTIONS) == 600
    ids = [row['QuestionID'] for row in place_value_seed.QUESTIONS]
    assert len(set(ids)) == 600
    assert all(sum(row['Level'] == level for row in place_value_seed.QUESTIONS) == 30 for level in range(1, 21))


def test_place_value_default_start_levels_by_year_group():
    strand = SimpleNamespace(code='PV')
    assert {
        year_group: _default_start_level(SimpleNamespace(year_group=year_group), strand)
        for year_group in range(0, 7)
    } == {0: 1, 1: 2, 2: 5, 3: 6, 4: 10, 5: 12, 6: 15}


def test_base_ten_metadata_is_mathematically_exact():
    assert _row('PV03-01')['VisualData']['blocks'] == {'ten': 8, 'one': 7}
    assert _row('PV06-01')['VisualData']['blocks'] == {'hundred': 4, 'ten': 2, 'one': 6}
    assert _row('PV10-03')['VisualData']['blocks'] == {'thousand': 3, 'hundred': 5, 'one': 4}
    assert _row('PV07-05')['VisualData']['after'] == {'hundred': 4, 'ten': 0, 'one': 0}


def test_number_line_endpoints_intervals_and_decimal_position_are_exact():
    early = _row('PV01-01')['VisualData']
    assert [tick['value'] for tick in early['ticks']] == [0, 1, 2, 3, 4]
    assert early['ticks'][3]['label'] is None

    boundary = _row('PV11-01')['VisualData']
    assert [tick['value'] for tick in boundary['ticks']] == [9998, 9999, 10000, 10001, 10002, 10003]
    assert boundary['jumps'] == 5

    decimal = _row('PV20-17')['VisualData']
    assert decimal['ticks'][0]['value'] == 0.3
    assert decimal['ticks'][-1]['value'] == 0.4
    assert decimal['marker']['value'] == 0.375
    assert decimal['marker']['position'] == 75


def test_equals_sign_variation_is_preserved_verbatim():
    questions = {row['Question'] for row in place_value_seed.QUESTIONS}
    assert '7 + 80 = __' in questions
    assert '__ = 30 + 8' in questions
    assert '87 = __ tens and __ ones.' in questions
    assert '__ + 80 = 87' in questions


def test_multiple_choice_and_comparison_controls_are_structured():
    choice = question_presentation(_question('PV03-03'))
    assert choice['answer_kind'] == 'choice'
    assert choice['text'] == 'Which shows 63?'
    assert [option['value'] for option in choice['options']] == ['A', 'B', 'C']
    assert choice['options'][0]['label'] == '6 tens and 3 ones'

    comparison = question_presentation(_question('PV05-08'))
    assert comparison['answer_kind'] == 'choice'
    assert [option['value'] for option in comparison['options']] == ['<', '>', '=']


def test_answer_checking_accepts_only_harmless_formatting_differences():
    assert answers_match('1,000', '1000')
    assert answers_match('1.0', '1')
    assert answers_match('0.70', '0.7')
    assert answers_match('8 9', '8, 9')
    assert answers_match('TRUE', 'True')
    assert answers_match('False', 'False; it is worth 60')
    assert answers_match('No', 'No; 500 is halfway')
    assert answers_match('8th', 'the 8th tick including 300')
    assert answers_match('2', '2°C')
    assert not answers_match('0.5', '0.05')
    assert not answers_match('9, 8', '8, 9')
    assert not answers_match('>', '<')


def test_yes_no_and_true_false_questions_use_large_choice_controls():
    yes_no = question_presentation(_question('PV03-18'))
    true_false = question_presentation(_question('PV03-25'))
    assert [option['value'] for option in yes_no['options']] == ['Yes', 'No']
    assert [option['value'] for option in true_false['options']] == ['True', 'False']


def test_boundary_crossing_bank_covers_forward_and_backward_examples():
    questions = {row['Question'] for row in place_value_seed.QUESTIONS}
    assert 'Complete: 98, 99, __, __.' in questions
    assert 'Complete: 1,002, 1,001, 1,000, __, __.' in questions
    assert 'Complete: 9,998, 9,999, __, __.' in questions
    assert 'Complete: 10,001, 10,000, __, __.' in questions


def test_every_explicit_rendering_note_has_structured_visual_data():
    noted = [row for row in place_value_seed.QUESTIONS if row['RenderingSuggestion']]
    assert len(noted) == 84
    assert all(row['VisualData'] and row['VisualData']['kind'] for row in noted)
    charts = [row['VisualData'] for row in noted if row['VisualData']['kind'] == 'place_value_chart']
    assert charts
    assert all(chart['values'] for chart in charts)


def test_every_visual_configuration_renders_through_shared_template():
    templates = Path(__file__).parents[1] / 'app' / 'templates'
    template = Environment(loader=FileSystemLoader(templates), autoescape=True).get_template(
        'fundamentals_question_visual.html'
    )
    for row in place_value_seed.QUESTIONS:
        if not row['VisualData']:
            continue
        rendered = template.render(presentation=question_presentation(_question(row['QuestionID'])))
        assert f"pv-visual-{row['VisualData']['kind']}" in rendered
