# One-paper assessments

In **Assessment Setup**, select the academic year, year group, subject and term. Click **✕ Switch off** beside the paper you do not use, then **Preview impact** and **Apply change & recalculate**. Either paper can be switched off, but at least one must remain on. Click **✓ Use this paper** to restore it.

Only the enabled paper contributes to the assessment maximum, percentage and attainment band. A missing enabled score remains missing; zero counts as a score. Names, maximum marks and existing raw scores for disabled papers remain stored, so re-enabling a paper can use its saved marks. If that paper has no mark, the result becomes incomplete until it is entered.

Teacher entry disables the unused cells. CSV templates contain only enabled score columns; subject CSV imports and full-workbook calculations use the same calculation service. GAP sync excludes disabled papers, and assessment-health/data-quality checks use the required-paper configuration. Saved outcomes in other academic years remain unchanged.

The existing administrator review/confirm workflow still applies. Changes deliberately recalculate only the selected school, academic year, year group, subject and term.

## Migration and compatibility

`20261021_01_optional_assessment_papers.py` follows `20261005_01`. It adds two Boolean columns to `assessment_configurations`, defaulting both to true. It does not modify raw marks, snapshots, bands or legacy settings. Old snapshots without these fields continue to mean both papers were required. Legacy settings keep both papers enabled until an administrator explicitly saves a year-specific configuration.

The normal Render build must run migrations before serving this application version. No new environment variables or manual SQL are needed. No migration or deployment has been run against production.

## Validation

`tests/test_optional_assessment_papers.py` covers each paper used alone; blanks/zeros; rejecting both off; review before confirmation; preserved inactive marks and maxima; re-enabling; unchanged historical results; manual and live calculation; single-column CSV preview/confirmation; workbook calculations; CSV template columns; required-paper admin completeness; and migration preservation. The existing assessment, security, access, intervention and promotion suites are also run.

A clean disposable SQLite upgrade reaches `20261021_01`. JavaScript syntax and Python compilation are checked. Live Render/PostgreSQL and desktop/iPad release checks described in the final pilot report remain required.
