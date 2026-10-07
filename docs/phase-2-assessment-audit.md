# Phase 2 assessment audit — 5 October 2026

Audited repository main at aec2207, before implementation. Uploaded monolithic files are older than the repository and are not the implementation baseline.

## Current workflow

An assessment is a class/year/term/subject scope, not a standalone Assessment record. SubjectResult is unique per pupil/year/term/subject. AssessmentSetting is a reusable year-group/subject/term template. Maths uses Arithmetic + Reasoning (40+35 defaults), Reading Paper 1 + Paper 2 (30+20), SPaG Spelling + Grammar (20+30). Both scores are required for a total; zero is valid. Percentages display to one decimal. Intentional labels are Working Towards / On Track / Exceeding; lower-year papers force WT. Writing is a separate teacher judgement. GAP stores question scores and can write paper totals. Year 6 usual assessments and SATs are separate: SATs has exam tabs, raw/scaled columns and a separate simple tracker. Active automatic interventions are the closest six below the combined pass percentage; a fixed 40% arithmetic rule is not present in this version.

Manual entry bulk saves; settings can be edited by teachers, admin forms and autosave. Combined CSV supports school roster creation as well as results; manual results are protected. Admin XLSX supports Pupils, Maths, Reading, SPaG, Phonics and SATs. Preview is rollback followed by re-upload; confirmation can be sent without preview. Some upload exceptions are caught after mutating rows, allowing partial changes to be committed.

## Findings

1. Combined CSV catches all exceptions per row without reverting that row, then flushes/commits successes and partial failed rows. Duplicate rows are not consistently rejected. CSV parsing lacks malformed structure/encoding checks.
2. Workbook writes totals independently, omits per-paper max validation, and commits before recalculation. Afterwards only Year 6 is recalculated, leaving other years' percentage/band stale. Unused FoundationResult.term access can crash this path. Unknown IDs can fall back to names. Preview data in cookies can contain pupil details and is not bound to confirmed content.
3. AssessmentSetting has school_id but its unique constraint and lookup omit school. Creating settings for a second school can conflict or use the first school's configuration.
4. Settings have no academic year. General admin updates recalculate all years; autosave changes settings without recalculating. Viewing dashboards may calculate bands using changed settings and promoted class year groups.
5. Band logic is duplicated in model helpers, teacher pages, reports and JavaScript. Some use saved bands, others recompute. Lower-year overrides are omitted by some imports/recalculations. Maxima can disagree with combined max. The on-track field is stored but the below-ARE field actually defines the expected boundary.
6. AssessmentValidationError subclasses ValueError; manual-entry catch order hides useful validation messages. Blank rows delete existing results. GET requests sync and commit interventions. Missing-score/configuration status and save state are unclear.
7. GAP can sync partial question sums and bypass paper validation; integer subject columns cannot faithfully store fractional question sums. SATs must stay separate from percentage-based term assessments.

## Proposed implementation

Keep existing schema/data and legacy template values. Add school/year/group/subject/term configurations, nullable result snapshots and server-side review records through one Alembic revision. Legacy outcomes are read as stored, not silently rewritten. Explicit score edits/recalculations capture the configuration and cohort year. Add a central result writer for manual entry, CSV, workbook and GAP. Preserve one-decimal band comparison and existing labels/closest-six intervention behaviour.

Move assessment configuration to Admin → Assessment Setup. Preview changes and affected bands; explicitly confirm the selected year's recalculation. Reject changed maxima that invalidate existing scores. Protect review records with owner/school checks, expiry, one-use confirmation and a database fingerprint; confirmation revalidates and writes/audits in one transaction. Preview never persists pupil/result changes. Keep admin combined roster provisioning visible in preview, while teacher assessment imports never create unknown pupils. Reject ambiguous, duplicate, malformed and invalid rows.

Improve bulk entry with visible maxima, server-calculated preview values, keyboard/paste support, missing-score health and unsaved/saved state. Keep SATs scaled calculation separate. Reuse AuditLog. Do not offer Undo without dependable snapshots across roster, history, tracker and intervention updates; a reverse import could undo later legitimate edits. Prefer explicit reviewed corrections for this phase.

Implementation outcome: see [Phase 2 delivery report](phase-2-assessment-delivery.md). The historical settings concerns were resolved with additive year configurations and nullable snapshots, not a destructive settings migration.
