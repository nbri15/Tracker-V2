"""Presentation and answer handling for Maths Fundamentals questions."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.models import FundamentalQuestion


LETTER_ANSWER = re.compile(r'^[A-D]$', re.IGNORECASE)
INLINE_OPTION = re.compile(r'\b([A-D])\)\s*(.*?)(?=\s+[A-D]\)|$)', re.DOTALL)
NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$')


def _clean(value: str | None) -> str:
    return ' '.join((value or '').replace('\u2212', '-').strip().split())


def _decimal(value: str | None) -> Decimal | None:
    cleaned = _clean(value).replace(',', '').replace('£', '')
    if not NUMBER.fullmatch(cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _numeric_sequence(value: str | None) -> list[Decimal] | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    if ',' in cleaned or ';' in cleaned:
        pieces = re.split(r'\s*[,;]\s*', cleaned)
    else:
        pieces = cleaned.split()
    if len(pieces) < 2:
        return None
    values = [_decimal(piece) for piece in pieces]
    return values if all(item is not None for item in values) else None


def _money(value: str | None) -> Decimal | None:
    cleaned = _clean(value).replace(',', '').replace('£', '')
    if cleaned.casefold().endswith('p'):
        pennies = _decimal(cleaned[:-1])
        return pennies / 100 if pennies is not None else None
    return _decimal(cleaned)


def answers_match(
    pupil_answer: str | None,
    correct_answer: str | None,
    *,
    accepted_answers: list[str] | None = None,
    answer_type: str | None = None,
) -> bool:
    """Compare answers while preserving mathematical distinctions."""

    pupil = _clean(pupil_answer)
    correct = _clean(correct_answer)
    if not pupil:
        return False

    if (answer_type or '').casefold() == 'money':
        pupil_number = _money(pupil)
        correct_number = _money(correct)
    else:
        pupil_number = _decimal(pupil)
        correct_number = _decimal(correct)
    if pupil_number is not None and correct_number is not None:
        return pupil_number == correct_number

    leading_choice = re.match(r'^(true|false|yes|no)\b', correct, re.IGNORECASE)
    if leading_choice and pupil.casefold() == leading_choice.group(1).casefold():
        return True

    ordinal_tick = re.match(r'^the\s+(\d+)(?:st|nd|rd|th)\s+tick\b', correct, re.IGNORECASE)
    if ordinal_tick and re.fullmatch(rf'{ordinal_tick.group(1)}(?:st|nd|rd|th)?', pupil, re.IGNORECASE):
        return True

    temperature = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*°?c', correct, re.IGNORECASE)
    if temperature and _decimal(pupil) == _decimal(temperature.group(1)):
        return True

    pupil_sequence = _numeric_sequence(pupil)
    correct_sequence = _numeric_sequence(correct)
    if pupil_sequence is not None and correct_sequence is not None:
        return pupil_sequence == correct_sequence

    def normalise_text(value: str) -> str:
        value = value.casefold().replace('’', "'")
        value = re.sub(r'\s*([+=\-])\s*', r'\1', value)
        value = re.sub(r'\s*([,;])\s*', r'\1', value)
        value = re.sub(r'\s+', ' ', value)
        return value.strip(' .')

    acceptable = [correct, *(accepted_answers or [])]
    pupil_text = normalise_text(pupil)
    if any(pupil_text == normalise_text(candidate) for candidate in acceptable if candidate):
        return True

    if (answer_type or '').casefold() == 'choice':
        equivalent_choices = {
            'mental place-value addition': 'mental place-value calculation',
            'mental place-value subtraction': 'mental place-value calculation',
            'column addition': 'column calculation',
            'column subtraction': 'column calculation',
            'subtraction / difference': 'subtraction',
            'find the difference / count on': 'count on / find the difference',
        }
        pupil_text = equivalent_choices.get(pupil_text, pupil_text)
        return any(
            pupil_text == equivalent_choices.get(normalise_text(candidate), normalise_text(candidate))
            for candidate in acceptable
            if candidate
        )
    return False


def _inline_options(question_text: str) -> tuple[str, list[dict]]:
    matches = list(INLINE_OPTION.finditer(question_text))
    if not matches:
        return question_text, []
    stem = question_text[:matches[0].start()].strip()
    options = [
        {'value': match.group(1).upper(), 'label': match.group(2).strip()}
        for match in matches
    ]
    return stem, options


def question_presentation(question: FundamentalQuestion) -> dict:
    """Return a safe, reusable pupil presentation for one stored question."""

    text = (question.question_text or '').strip()
    answer = _clean(question.answer)
    answer_type = _clean(getattr(question, 'answer_type', None)).casefold()
    visual = getattr(question, 'visual_data', None)
    stem, options = _inline_options(text)
    visual_options = (visual or {}).get('options') or []
    if visual_options:
        options = [{'value': option, 'label': option} for option in visual_options]
    if answer_type == 'choice' and options:
        answer_kind = 'choice'
        display_text = stem if stem != text else text
    elif answer_type == 'boolean':
        answer_kind = 'choice'
        labels = ('Yes', 'No') if answer.casefold() in {'yes', 'no'} else ('True', 'False')
        options = [{'value': label, 'label': label} for label in labels]
        display_text = text
    elif LETTER_ANSWER.fullmatch(answer) and options:
        answer_kind = 'choice'
        display_text = stem
    elif re.match(r'^(true|false)\b', answer, re.IGNORECASE):
        answer_kind = 'choice'
        options = [{'value': 'True', 'label': 'True'}, {'value': 'False', 'label': 'False'}]
        display_text = text
    elif re.match(r'^(yes|no)\b', answer, re.IGNORECASE):
        answer_kind = 'choice'
        options = [{'value': 'Yes', 'label': 'Yes'}, {'value': 'No', 'label': 'No'}]
        display_text = text
    elif answer.casefold() in {'always', 'sometimes', 'never'}:
        answer_kind = 'choice'
        options = [
            {'value': 'Always', 'label': 'Always'},
            {'value': 'Sometimes', 'label': 'Sometimes'},
            {'value': 'Never', 'label': 'Never'},
        ]
        display_text = text
    elif answer in {'<', '>', '='}:
        answer_kind = 'choice'
        options = [{'value': symbol, 'label': symbol} for symbol in ('<', '>', '=')]
        display_text = text
    elif answer.casefold() in {'chart a', 'chart b'}:
        answer_kind = 'choice'
        options = [{'value': 'Chart A', 'label': 'Chart A'}, {'value': 'Chart B', 'label': 'Chart B'}]
        display_text = text
    elif answer_type == 'money':
        answer_kind = 'money'
        display_text = text
    elif answer_type in {'integer', 'decimal'}:
        answer_kind = 'numeric'
        display_text = text
    elif _numeric_sequence(answer) is not None:
        answer_kind = 'sequence'
        display_text = text
    elif _decimal(answer) is not None:
        answer_kind = 'numeric'
        display_text = text
    else:
        answer_kind = 'text'
        display_text = text

    return {
        'text': display_text,
        'answer_kind': answer_kind,
        'options': options,
        'visual': visual,
        'visual_alt': question.rendering_notes or question.question_text,
        'representation_type': question.representation_type,
        'mastery_focus': question.mastery_focus,
        'stem_reasoning_prompt': getattr(question, 'stem_reasoning_prompt', None),
        'misconception_target': getattr(question, 'misconception_target', None),
        'input_prefix': '£' if answer_kind == 'money' else None,
    }
