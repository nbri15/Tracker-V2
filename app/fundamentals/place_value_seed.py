"""Authoritative Place Value seed data generated from the mastery workbook."""

from __future__ import annotations

import json
from pathlib import Path


_DATA_PATH = Path(__file__).with_name('place_value_seed.json')
with _DATA_PATH.open(encoding='utf-8') as source_file:
    _DATA = json.load(source_file)

STRANDS = _DATA['strands']
LEVELS = _DATA['levels']
QUESTIONS = _DATA['questions']
REPRESENTATION_GUIDANCE = _DATA['representation_guidance']
SOURCE = _DATA['source']
