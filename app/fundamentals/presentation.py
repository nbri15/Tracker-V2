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
    cleaned = _clean(value).replace(',', '')
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


def answers_match(pupil_answer: str | None, correct_answer: str | None) -> bool:
    """Compare answers while preserving mathematical distinctions."""

    pupil = _clean(pupil_answer)
    correct = _clean(correct_answer)
    if not pupil:
        return False

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
        value = re.sub(r'\s*([,;])\s*', r'\1', value)
        value = re.sub(r'\s+', ' ', value)
        return value.strip(' .')

    return normalise_text(pupil) == normalise_text(correct)


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
    stem, options = _inline_options(text)
    if LETTER_ANSWER.fullmatch(answer) and options:
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
        'visual': question.visual_data,
        'visual_alt': question.rendering_notes or question.question_text,
        'representation_type': question.representation_type,
        'mastery_focus': question.mastery_focus,
    }
