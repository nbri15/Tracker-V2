# Phase 2: Assessment Reliability & UX

## Audit

The [pre-implementation audit](phase-2-assessment-audit.md) traces creation/configuration, paper structures, manual entry, CSV/XLSX imports, saved outcomes, reports, GAP, interventions and Year 6 SATs. The main causes of unreliable uploads were partial row mutations after exceptions, confirmation without a bound preview, and workbook totals/recalculation differing from other result writers. Historical reports could also change when shared thresholds or live class year groups changed.

## Changes

- One result writer validates scores, combines papers, rounds percentages, applies existing bands and the lower-year-paper rule, and records the configuration/cohort used. Manual scores, teacher CSV, admin CSV, core workbook results and GAP use it. Reports read saved outcomes instead of recalculating them with today's class/settings. SATs retains its separate three-paper maths structure and raw/scaled rules; CSV and workbook share its writer.
- **Admin → Assessment Setup** selects school/year/group/subject/term. Two paper maxima give a calculated combined maximum; AT and GDS boundaries are explicit. Invalid percentages/maxima and contradictory configurations cannot be saved. General Settings keeps school academic-year controls. Teacher settings editing and silent admin autosave are closed.
- **Preview impact → confirm → recalculate** shows checked/changed/unchanged results and affected pupils. Incompatible maximum reductions block confirmation. Only the selected school/year/cohort/subject/term is recalculated. Current-year automatic closest-six interventions refresh; historical intervention records stay untouched.
- **Upload → validate → preview → confirm → import** uses a server-side review tied to the exact upload, user, school and baseline data. Duplicate/ambiguous/unknown pupil identities, mismatched IDs/classes, malformed files and invalid scores block imports. Missing/blank rows are reported. Teacher imports never create pupils; admin combined roster imports clearly show proposed new pupils. Existing manual/GAP results require an explicit replacement option on teacher upload and remain protected in combined CSV. Blank workbook scores retain existing results. All domain writes and audit events commit together or roll back together.
- Reviews expire after 30 minutes and cannot be confirmed twice. Confirmation checks current database state and revalidates. A school row lock serializes the new save paths on PostgreSQL. Temporary review payloads are removed on success; expired reviews older than a day are pruned for that school when a new review is created. Durable audit entries stay in AuditLog.
- Manual entry shows actual per-row maxima, saved configuration in outcome tooltips, missing scores, clear-score confirmation and unsaved/saved state. Tab/Enter and two-column spreadsheet paste are supported. Live derived outcomes come from the server, with local whole-number/range validation; saving validates again. A database failure never reports success or silently discards the submitted values.
- Health shows **Draft / Incomplete / Complete / Configuration problem**, with the class's valid-score count and named reasons. Subgroup filters do not make the whole class appear complete.
- GAP sync requires complete whole-mark paper totals and matching configured question maxima. Fractional marks remain in GAP and are not truncated into integer assessment scores. GAP template uniqueness now includes school, and a foreign question ID cannot be attached to another school's template.
- Lightweight audit events cover creation, imports, bulk changes, thresholds, configuration and recalculation. The admin setup page displays recent assessment history.

## Workflow descriptions

| Screen | What teachers/admins see |
|---|---|
| Teacher Maths/Reading/SPaG | Health count and missing-score reasons; configuration summary; downloadable class CSV; validated upload; one bulk results grid with names, per-paper maxima, total, percentage, band, test level, progress and notes. |
| Teacher upload preview | Matched/new/update counts; missing or blank pupils; every affected row's planned action/outcome; blocking errors disable Confirm import. |
| Assessment Setup | Academic year, group, subject and term selectors; named paper maxima; combined maximum; AT/GDS percentages and equivalent raw boundaries; recent audit history. |
| Setup impact review | Current/proposed maxima and thresholds; number checked, changed and unchanged; named band changes; Apply change & recalculate or Cancel. |
| Completion | Explicit added/updated/failed/missing-score feedback; direct return to the teacher assessment, setup or admin import/class assessment area. |

Screenshots are unavailable: the environment had no runnable browser and the Chromium download returned an invalid archive. HTTP/template workflows were exercised by automated tests; JavaScript syntax was checked. Desktop/iPad keyboard, clipboard and visual behaviour still needs a real browser smoke test before production rollout.

## Migration

`20261005_01_assessment_reliability.py`, following `20260922_01`:

1. Adds assessment_configurations with school/year/group/subject/term uniqueness.
2. Adds short-lived assessment_reviews.
3. Adds nullable configuration_snapshot and cohort_year_group to subject_results.
4. Replaces GAP template's old global unique key with a school-inclusive key.

No result, intervention, GAP score, SATs score or legacy setting value is deleted, reset or recalculated by this migration. No thresholds are silently backfilled. Original thresholds cannot be reconstructed for legacy rows; their saved bands remain authoritative. An explicit subsequent edit/recalculation captures a snapshot. The migration supports adoption of already-created test schemas. Automatic schema downgrade is refused to prevent dropping the new history/configuration data; rolling back application code does not require a schema downgrade.

## Validation

**107 tests passed**, including **62 new Phase 2 cases**. Coverage includes all subject structures, zero/blank/max/over-max values, AT/GDS boundaries, threshold impact/apply, lower-year papers, malformed/duplicate/unmatched/foreign-school imports, read-only previews, actual confirmation, stale/expired/replayed reviews, protected scores, bulk rollback, failed database commit rollback, historical cohort/outcome preservation, permissions/CSRF, GAP incomplete/fractional totals, active SATs import/scaled boundaries and full workbook round-trip. Migration tests exercise both a clean upgrade and preservation of seeded legacy results/settings/interventions/pupils.

The existing September rollover test was also corrected to use an explicit September date. It failed identically on unchanged main when run in October; no rollover application behaviour was changed.

Python compilation, JavaScript syntax and `git diff --check` passed. Migration/runtime tests used isolated SQLite databases, not production or a PostgreSQL staging database. Existing dependency deprecation warnings remain.

## Remaining limits and safety decisions

- **Undo last import is intentionally omitted.** Imports can touch roster fields, class histories, tracker rows and interventions. Without versioned before-images and conflict protection for every touched record, reversing one could undo later legitimate edits. Preview, atomic save, conflict checking and audit protection are provided; corrections use another reviewed import/manual save.
- Original configuration for legacy results may be unknown. Saved outcomes remain stable; an admin can deliberately recalculate a selected historical scope after reviewing impact. No automatic historical rewrite occurs.
- Workbook support covers roster/core results, Phonics and SATs. Populated Writing/Foundation/Reception/Times Tables sheets that this workbook importer did not previously implement are now explicitly blocked rather than silently ignored. Their existing dedicated trackers/import formats remain available. Empty placeholder sheets from the downloaded workbook are allowed.
- Import conflict detection conservatively fingerprints school data. Another school data edit can require a fresh review, even if unrelated to the uploaded assessment. This favours correctness; finer scope/version checks can follow once the workflow is established.
- PostgreSQL migration/locking and actual browser behaviour need staging checks. Production data has not been accessed or altered.

## Render after merge

The repository's render.yaml already specifies:

```sh
pip install -r requirements.txt && flask --app wsgi:app db upgrade
```

Ensure the actual Render service's **Build Command** also contains that migration command; a dashboard override may differ from the YAML. Deploy the merged commit, and check the deploy logs show the upgrade to **20261005_01** before Gunicorn starts. This can be done from the Render dashboard without shell access. No assessment seeding, SQL column creation or database reset is needed. No new runtime dependency or environment variable is introduced.

Before production rollout, apply the migration to a PostgreSQL staging copy/backup and smoke-test one teacher assessment, invalid and valid import previews, setup impact/recalculation, a historical year and Year 6 SATs. Confirm school isolation using two accounts. If a build migration fails, resolve it through Alembic and redeploy; do not reset/reseed the school database.

## Phase 3 GAP priorities

1. Version question templates by school/year/assessment and connect each paper's full question maximum to its configured maximum.
2. Show missing-question completion separately from attainment, with strand-level denominators and item-level validation.
3. Provide a reviewed QLA CSV/XLSX import with the same confirm/transaction/audit protections.
4. Add useful skill/strand summaries and intervention suggestions that distinguish incomplete evidence from a demonstrated gap.
5. Add drill-down from a pupil band to the exact paper scores, question evidence and configuration used.
