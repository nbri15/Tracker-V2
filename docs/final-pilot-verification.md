# Class Compass: final verification, 21 October 2026

## Scope and evidence

Reviewed `nbri15/Tracker-V2` main at `aac745f5873f9041da1ee97fd61635151c307738`, the merged PR descriptions/diffs for [#174](https://github.com/nbri15/Tracker-V2/pull/174), [#175](https://github.com/nbri15/Tracker-V2/pull/175), [#176](https://github.com/nbri15/Tracker-V2/pull/176), [#177](https://github.com/nbri15/Tracker-V2/pull/177), [#179](https://github.com/nbri15/Tracker-V2/pull/179), [#180](https://github.com/nbri15/Tracker-V2/pull/180), [#182](https://github.com/nbri15/Tracker-V2/pull/182), [#185](https://github.com/nbri15/Tracker-V2/pull/185) and [#186](https://github.com/nbri15/Tracker-V2/pull/186), and the current implementation/tests/migrations. GitHub comparison confirmed that the existing local assessment implementation is identical to current main; only the psycopg dependency differs from the local base commit. Both installed PostgreSQL drivers were checked.

Tests used temporary databases and fictional pupils. No production credentials, database or pupil attachment was used. No existing migrations were rewritten. No Maths Fundamentals or foundational-knowledge implementation was changed. This is a completion/safety fix, not a rebuild.

## Classification of previous findings

Classification describes the condition found on main; confirmed defects below are corrected in this PR.

| Finding | Classification | Implementation evidence | Supporting test evidence |
|---|---|---|---|
| Production secret key | **Confirmed defect** | `config.py:Config.SECRET_KEY` supplied a public development default, accepted in production. `app/__init__.py:create_app` now refuses missing/default production secrets before database initialization. | `test_pilot_verification.py:test_production_rejects_missing_or_development_secret`, `test_production_accepts_private_key_and_hardens_cookies` |
| Session cookies | **Already fixed**, with explicit SameSite hardening added | `config.py:ProductionConfig` already enables Secure/HttpOnly; base config now explicitly sets session and remember cookies to SameSite=Lax. | `test_production_accepts_private_key_and_hardens_cookies` |
| Actual Render secret/cookie configuration | **Potential risk requiring further testing** | Deployed environment and HTTPS cookies cannot be inspected through repository access. No secret has been generated or rotated by this PR. | Local configuration test above; real deployment checks below remain open. |
| CSRF | **Already fixed** (#175, #185) | `app/extensions.py:csrf`, `app/__init__.py:register_extensions`, CSRF fields/client handling in `app/templates/base.html`. New admin GAP forms include explicit tokens. | `test_security_hardening.py:test_csrf_rejects_unprotected_post`, `test_assessment_reliability.py:test_csrf_is_required_for_confirmation`, `test_gap_admin_save_requires_csrf` |
| Admin-only GAP definitions | **Confirmed defect** | `app/teacher/routes.py:gap_analysis` previously accepted question additions/definition changes from teachers. Definitions now use `app/assessment_workflow/routes.py:gap_templates`, guarded by admin role/school and enforced again in `app/services/gap.py:parse_question_columns`. Teachers retain score entry/sync. | `test_teacher_cannot_change_definitions_but_can_save_marks`, `test_administrator_cannot_edit_foreign_school_gap_template` |
| GAP question IDs and saved marks | **Confirmed defect** | `parse_question_columns` previously cascade-deleted omitted scored questions, permitted maximum reductions below saved marks/paper moves and could dereference an unknown ID. It now validates the complete edit first, preserves IDs and rejects destructive edits. | `test_admin_edit_preserves_ids_marks_and_adds_question`, `test_unsafe_definition_edit_is_rejected_without_loss`, `test_scored_question_cannot_be_omitted_or_replaced` |
| Ordinary assessment mark validation | **Already fixed** (#185) | `app/services/assessments.py:compute_subject_result_values`, `app/services/assessment_reliability.py:apply_result`, `app/services/assessment_imports.py`; raw values must be finite non-negative whole marks within maxima. | Existing `test_invalid_scores`, `test_manual_save_zero_blank_max_and_friendly_error`, `test_invalid_bulk_save_rolls_back_other_pupils`, `test_invalid_imports_never_leave_partial_rows` |
| GAP mark validation and transaction safety | **Already fixed** for numeric limits; **Confirmed defect** for omitted cells | `app/services/gap.py:save_gap_scores` rejects invalid numeric values. Omitted cells previously deleted saved marks; now omission preserves them and totals are rebuilt from all saved marks. Explicit blank still clears the selected cell; zero is a mark. | `test_invalid_gap_mark_rolls_back_the_whole_save`, `test_partial_gap_submission_retains_omitted_marks_and_correct_total`, existing `test_gap_sync_does_not_use_incomplete_or_fractional_totals` |
| Historical class membership/results | **Already fixed** (#174/#177/#182/#185) | `app/services/assessments.py:get_class_pupil_query`, `app/services/admin_ops.py:snapshot_pupil_history`, `app/services/assessment_reliability.py:apply_result/setting_for_result`; saved bands/configuration snapshots are authoritative. | Existing `test_legacy_bands_do_not_change_on_view_or_promotion`, `test_old_cohort_survives_manual_edit_after_promotion`, `test_threshold_preview_confirm_preserves_history_and_lower_year`, `test_explicit_rollover_advances_once_and_preserves_history` |
| Repeated/stale promotion | **Already fixed** (#182) | `app/services/admin_ops.py:promote_pupils_to_next_year` locks/reloads the school and checks stored source year; `app/admin/routes.py:promotion` requires source-year confirmation. | Existing `test_promotion_advances_only_the_selected_schools_working_year`, `test_explicit_rollover_advances_once_and_preserves_history`, `test_two_schools_keep_independent_years_and_cohorts` |
| Migration process/startup | **Already fixed** in repository (#179/#182/#185/#186); real PostgreSQL execution is **Potential risk requiring further testing** | `render.yaml` upgrades before Gunicorn; existing `20261005_01_assessment_reliability.py` adds snapshots without recalculating old scores. `requirements.txt` includes both PostgreSQL drivers. No schema edits in this PR. Startup still has existing academic-year/gender normalization and optional explicitly configured bootstrap/demo behavior; it is not claimed to perform zero writes on a populated database. | Existing `test_migration_preserves_legacy_results_and_other_data`, `test_application_restart_never_changes_stored_year`; fresh local production-config upgrade to `20261005_01`; PostgreSQL DDL compilation/driver initialization test. |
| Missing versus zero | **Already fixed** in result calculations; **Confirmed defect** in admin summary | `app/admin/routes.py:data_quality` previously considered any SubjectResult row sufficient. It now counts a pupil as incomplete until all three core subjects have both marks and saved outcomes; zero remains valid. This summary concerns the ordinary core-subject tracker; SATs has a separate tracker. | Existing `test_zero_blank_and_boundaries`, new `test_missing_scores_require_all_subjects_and_accept_zero` |
| Intervention thresholds | **Already fixed** (#185) | `app/services/interventions.py:suggest_interventions_for_scope` uses each result's stored configuration, and GET views do not regenerate flags. It uses the existing closest-six-below-threshold policy; no new arithmetic-40% policy was introduced. | `test_interventions_use_saved_threshold_and_never_reflag_on_get`; assessment threshold/history regressions. |
| Intervention PDF export | **Confirmed defect** | `app/admin/routes.py:interventions` referenced nonexistent `focus_area`, crashing when rows existed. It now uses the existing `reason` field. No intervention schema changed. | `test_populated_intervention_pdf_uses_existing_reason_and_is_school_scoped` (captures the populated export rows; does not claim visual PDF/browser verification). |
| Cross-school/class access | **Already fixed** for tested existing paths (#175/#176/#185); new admin GAP path explicitly scoped | `app/utils.py:school_scoped_query/require_same_school`, `app/pupils/routes.py:profile/_can_view_pupil`, teacher class scoping, `app/assessment_workflow/routes.py:load_review` and new `gap_templates`. | Existing foreign-pupil/review-owner/school-settings/import tests; new `test_other_class_profile_and_intervention_edit_are_rejected`, `test_admin_foreign_question_and_teacher_foreign_scores_are_blocked`, `test_administrator_cannot_edit_foreign_school_gap_template`, `test_pilot_pages_and_exports_do_not_include_other_school` |
| Rebuilding/reworking Maths Fundamentals | **Not applicable** | Explicitly excluded from this request. Existing infrastructure dependencies remain untouched. | Dedicated Fundamentals test modules excluded from this focused verification. |

All named new tests are in `tests/test_pilot_verification.py`. Existing assessment tests are in `tests/test_assessment_reliability.py`; rollover tests are in `tests/test_school_working_academic_year.py` and `tests/test_admin_controlled_academic_year.py`.

## Changes actually made

1. Refuse the missing/public development key in production and explicitly configure SameSite cookies. Keep the existing production key to preserve sessions.
2. Provide a small administrator-only GAP definition editor linked from the existing admin sidebar; keep teacher marks entry and existing templates.
3. Preserve scored question IDs, reject unknown/duplicate IDs and destructive definition edits; preserve omitted cells and recalculate totals from the saved marks.
4. Correct the ordinary core-tracker missing-scores count, including partial/zero cases.
5. Repair the populated intervention PDF export's nonexistent field reference.
6. Add focused regressions and this evidence report. No migration, schema backfill, seed, live update or foundational-maths work.

## Validation

**Final focused suite: 121 passed, 0 failed; 38 new regression cases.** Run it with:

```bash
python -m pytest -q tests/test_security_hardening.py tests/test_pilot_verification.py tests/test_assessment_reliability.py tests/test_access_imports_and_pupil_delete.py tests/test_admin_controlled_academic_year.py tests/test_school_working_academic_year.py tests/test_working_year_repair.py tests/test_operational_safety.py
```

The initial 37 new cases were also run against an untouched pre-fix snapshot: **15 failed and 22 passed**. These deliberate baseline failures reproduce unsafe-key acceptance, GAP permission/preservation/input failures, the missing-scores count and populated intervention PDF crash. They are not unresolved failures on the fixed branch. One further cross-school template regression was added subsequently.

Additional checks: Python compilation; `git diff --check`; a clean disposable SQLite database upgraded using production configuration and the existing Flask CLI; current revision `20261005_01` (single head). The startup regression verifies no tables are created when the database is empty. Both psycopg and psycopg2 SQLAlchemy engines initialize without connecting; all mapped table definitions compile for the PostgreSQL dialect. These checks are not a substitute for executing migrations on PostgreSQL.

A PostgreSQL 16 binary was obtained for a disposable local run, but PostgreSQL cannot run as root and the container denies switching to a non-root user (`runuser: cannot set groups: Operation not permitted`). No PostgreSQL upgrade, row-lock concurrency or actual database restore is claimed. Backup scripts were reviewed and their shell syntax/input guards were checked previously; no real backup has been restored.

No live Render login, deployment logs, environment configuration, real desktop/iPad browser session or production backup was available. Automated HTTP tests do not establish browser layout, PDF appearance or iPad usability. Ordinary SQLAlchemy/Alembic deprecation warnings remain; they are not test failures.

## Pilot decision and final three tasks

**Code is a candidate for a small supervised school pilot after this PR is reviewed and the release checks below pass. It is not yet verified ready for an unattended live rollout.** The goal is release verification, not another feature phase.

1. Review/approve this PR. Before an approved deployment, confirm Render has an existing private `SECRET_KEY`, production mode and the intended Python version, that the actual build command upgrades the intended database, and that deployment reaches `20261005_01` before Gunicorn. Do not rotate the key unnecessarily.
2. In a separate PostgreSQL staging database, verify migration from the deployed revision with fictional/anonymised data, preserved result counts/bands/GAP IDs, repeated/concurrent promotion safeguards, and a real backup/restore drill. Never rehearse recovery against production.
3. On desktop and a school iPad, use fictional admin/teacher accounts to enter one assessment, reject an invalid upload, confirm a valid upload, check an old year, edit GAP definitions as admin and scores as teacher, view an intervention and export its PDF. Then limit the first pilot to one class and check the totals with the teacher.

No merge, deployment or production database action is authorized or performed by this report/PR.
