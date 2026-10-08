"""Addition & Subtraction workbook, presentation and visual coverage."""

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from app.fundamentals import addition_subtraction_seed
from app.fundamentals.presentation import answers_match, question_presentation
from app.fundamentals.routes import _default_start_level


def _row(question_id):
    return next(row for row in addition_subtraction_seed.QUESTIONS if row['QuestionID'] == question_id)


def _question(question_id):
    row = _row(question_id)
    return SimpleNamespace(
        question_text=row['Question'], answer=row['Answer'], answer_type=row['AnswerType'],
        accepted_answers=row['AcceptedAnswers'], visual_data=row['VisualData'],
        rendering_notes=row['RenderingSuggestion'], representation_type=row['RepresentationType'],
        mastery_focus=row['MasteryFocus'], stem_reasoning_prompt=row['StemReasoningPrompt'],
        misconception_target=row['MisconceptionTarget'],
    )


def test_authoritative_addition_subtraction_dataset_counts_ids_and_metadata():
    assert addition_subtraction_seed.SOURCE == {
        'workbook': 'Class_Compass_Addition_Subtraction_Fundamentals_Mastery.xlsx',
        'question_sheet': 'Mastery Question Bank', 'question_count': 660, 'level_count': 22,
    }
    assert len(addition_subtraction_seed.LEVELS) == 22
    assert len(addition_subtraction_seed.QUESTIONS) == 660
    ids = [row['QuestionID'] for row in addition_subtraction_seed.QUESTIONS]
    assert len(set(ids)) == 660
    assert ids[0] == 'AS01-01'
    assert ids[-1] == 'AS22-30'
    assert all(sum(row['Level'] == level for row in addition_subtraction_seed.QUESTIONS) == 30 for level in range(1, 23))
    assert all(row['AnswerType'] in {'integer', 'decimal', 'money', 'text', 'boolean', 'choice'} for row in addition_subtraction_seed.QUESTIONS)


def test_addition_subtraction_default_start_levels_match_workbook():
    strand = SimpleNamespace(code='AS')
    assert {
        year_group: _default_start_level(SimpleNamespace(year_group=year_group), strand)
        for year_group in range(0, 7)
    } == {0: 1, 1: 1, 2: 3, 3: 7, 4: 10, 5: 14, 6: 16}


def test_equals_sign_and_unknown_positions_are_preserved_verbatim():
    questions = {row['Question'] for row in addition_subtraction_seed.QUESTIONS}
    assert '__ + 7 = 15' in questions
    assert '15 = __ + 6' in questions
    assert '14 - __ = 9' in questions
    assert '__ = 17 - 8' in questions


def test_bridge_ten_visuals_preserve_partition_steps():
    addition = _row('AS04-01')['VisualData']
    subtraction = _row('AS05-01')['VisualData']
    assert addition['params'] == {'start': '8', 'add': '5', 'to_ten': '2', 'remainder': '3'}
    assert subtraction['params'] == {'start': '13', 'remove_to_10': '3', 'remove_remaining': '2'}


def test_part_whole_difference_and_number_line_metadata_are_exact():
    part_whole = _row('AS01-07')['VisualData']
    assert part_whole['params'] == {'whole': '5', 'parts': '2,?'}
    difference = _row('AS06-11')['VisualData']
    assert difference['category'] == 'comparison'
    assert difference['params'] == {'larger': '7', 'smaller': '5', 'difference': '?'}
    line = _row('AS06-07')['VisualData']['line']
    assert line['points'] == [9, 13]
    assert line['jumps'] == [4]


def test_dienes_exchange_and_exchange_through_zero_preserve_value():
    addition = _row('AS11-01')['VisualData']
    assert addition['combined_ones'] == 13
    assert addition['result_blocks'] == {'ten': 4, 'one': 3}
    subtraction = _row('AS13-01')['VisualData']
    assert subtraction['top_blocks'] == {'ten': 5, 'one': 2}
    assert subtraction['exchanged_blocks'] == {'ten': 4, 'one': 12}
    assert subtraction['result_blocks'] == {'ten': 2, 'one': 5}
    through_zero = _row('AS17-12')['VisualData']['column']
    assert through_zero['exchanged'] == {'hundred': 4, 'ten': 9, 'one': 13}
    assert through_zero['result_value'] == 236


def test_column_methods_align_operands_and_retain_exchange_metadata():
    addition = _row('AS16-04')['VisualData']['column']
    subtraction = _row('AS17-05')['VisualData']['column']
    assert addition['top'] == '356'
    assert addition['bottom'] == '278'
    assert addition['operation'] == '+'
    assert addition['result_value'] == 634
    assert subtraction['top'] == '700'
    assert subtraction['bottom'] == '268'
    assert subtraction['operation'] == '−'
    assert subtraction['exchanged'] == {'hundred': 6, 'ten': 9, 'one': 10}


def test_decimal_money_boolean_choice_and_controlled_text_answers():
    assert answers_match('4.0', '4', answer_type='decimal')
    assert answers_match('£6.25', '6.25', answer_type='money')
    assert answers_match('625p', '6.25', answer_type='money')
    assert not answers_match('£6.20', '6.25', answer_type='money')
    alternative = _question('AS19-26')
    assert answers_match('count on', alternative.answer, accepted_answers=alternative.accepted_answers, answer_type='text')
    assert answers_match('find the difference', alternative.answer, accepted_answers=alternative.accepted_answers, answer_type='text')
    assert not answers_match('column subtraction', alternative.answer, accepted_answers=alternative.accepted_answers, answer_type='text')
    boolean = question_presentation(_question('AS02-28'))
    choice = question_presentation(_question('AS19-07'))
    money = question_presentation(_question('AS21-13'))
    assert boolean['answer_kind'] == 'choice'
    assert [option['value'] for option in boolean['options']] == ['True', 'False']
    assert choice['answer_kind'] == 'choice'
    assert 'Count on / find the difference' in [option['value'] for option in choice['options']]
    assert money['answer_kind'] == 'money'
    assert money['input_prefix'] == '£'


def test_every_selection_question_has_exactly_one_gradeable_correct_option():
    for row in addition_subtraction_seed.QUESTIONS:
        if row['AnswerType'] not in {'choice', 'boolean'}:
            continue
        presentation = question_presentation(_question(row['QuestionID']))
        matching_options = [
            option['value'] for option in presentation['options']
            if answers_match(option['value'], row['Answer'], accepted_answers=row['AcceptedAnswers'], answer_type=row['AnswerType'])
        ]
        assert len(matching_options) == 1, (row['QuestionID'], matching_options)


def test_every_renderer_spec_is_preserved_and_uses_the_shared_template():
    templates = Path(__file__).parents[1] / 'app' / 'templates'
    template = Environment(loader=FileSystemLoader(templates), autoescape=True).get_template('fundamentals_question_visual.html')
    visual_rows = [row for row in addition_subtraction_seed.QUESTIONS if row['RendererSpec']]
    assert len(visual_rows) == 458
    for row in visual_rows:
        assert row['VisualData']['raw'] == row['RendererSpec']
        assert row['VisualData']['category']
        rendered = template.render(presentation=question_presentation(_question(row['QuestionID'])))
        assert f"pv-visual-{row['VisualData']['kind']}" in rendered


def test_stem_and_misconception_metadata_are_not_discarded():
    assert sum(bool(row['StemReasoningPrompt']) for row in addition_subtraction_seed.QUESTIONS) == 88
    assert sum(bool(row['MisconceptionTarget']) for row in addition_subtraction_seed.QUESTIONS) == 56
    assert _row('AS01-01')['StemReasoningPrompt'] == '2 and 3 make __.'
    assert _row('AS01-21')['MisconceptionTarget']
