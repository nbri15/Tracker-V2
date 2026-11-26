"""CSV writers that stop spreadsheets treating exported text as a formula.

A cell such as ``=HYPERLINK(...)`` typed into a pupil note would otherwise run as a
formula when a teacher opens the export in Excel or Numbers. Text starting with
= + - @ (or a tab/carriage return) gets a leading apostrophe. Real numbers, including
negative ones like -5, are left exactly as they are.
"""

from __future__ import annotations

import csv

FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def safe_cell(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES) and not _looks_numeric(value):
        return "'" + value
    return value


class _SafeWriter:
    def __init__(self, inner):
        self._inner = inner

    def writerow(self, row):
        return self._inner.writerow([safe_cell(value) for value in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def writer(output, *args, **kwargs):
    return _SafeWriter(csv.writer(output, *args, **kwargs))


class DictWriter(csv.DictWriter):
    def writerow(self, rowdict):
        return super().writerow({key: safe_cell(value) for key, value in rowdict.items()})

    def writerows(self, rowdicts):
        for row in rowdicts:
            self.writerow(row)


def neutralise_workbook_formulas(workbook) -> None:
    """Store every formula-looking cell in an openpyxl workbook as plain text.

    Exports never contain intentional formulas, so anything openpyxl marked as a
    formula came from typed text (a pupil name, a note) and must stay text.
    """
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.data_type == 'f':
                    cell.data_type = 's'
