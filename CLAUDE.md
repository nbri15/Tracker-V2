# CLAUDE.md — Tracker-V2 (Class Compass)

## Ground rules (from the owner — always follow)

- The owner is a primary school teacher and hobby developer. Explain things in plain English and keep summaries short.
- **Test data must always be synthetic.** Never use, copy or invent realistic real pupil data. Use obviously fake names (e.g. "Synth Test", "Alice Test").
- **Work on a new branch. Never push to `main`.** Do not change anything that affects the live site (Render settings, Supabase, environment variables, GitHub Actions schedules, `render.yaml`, migrations that would run on deploy) without asking first.
- **Do not build the meeting minutes feature.** It is parked for later.
- **Maths Fundamentals is deliberately hidden.** Leave it hidden (`FUNDAMENTALS_ENABLED` stays off in production; don't add links to it).
- **Only say something is tested if the test was actually run.** Say plainly what was and wasn't run.

## What the app does

Class Compass is a multi-school assessment tracker for primary schools (Reception to Year 6). It runs as a
Flask website that teachers use on iPads as an installable home-screen web app.

Main features:
- **Assessment cycles**: Maths, Reading and SPaG scores per term (Autumn/Spring/Summer), two papers each,
  turned into a percentage and a band (Working Towards / On Track / Exceeding) using per-school settings.
  Optional papers and per-result "test level" are supported. Writing uses teacher-judged bands.
- **Gap analysis (QLA)**: per-question marks for each paper. When every question on a paper is filled in and the
  question maxima add up to the paper maximum, totals sync into the main subject results.
- **Interventions**: intervention records per pupil, intervention programmes, and an impact view.
- **SATs mode**: Year 6 can switch to a SATs tracker (`/sats/simple`) with multiple mock exams, raw and scaled scores.
- **Other trackers**: Phonics, Times tables (MTC), Reception (EYFS), Foundation subjects.
- **Academic-year rollover**: each school has its own working year (`schools.current_academic_year_id`).
  Admins snapshot class history then promote pupils (Year 6 become inactive leavers) at `/admin/promotion`.
- **Imports/exports**: CSV and Excel imports go through a review step before saving; CSV/PDF exports;
  a one-click whole-school backup ZIP.
- **Maths Fundamentals**: pupil quiz feature — hidden (see ground rules).

## Roles and multi-school separation

- `executive_admin` — platform owner, can see/manage all schools (`/exec/...`). Logs in **without** a school code.
  Has `school_id = NULL`; picks a school via `?school_id=` on admin pages.
- `school_admin` (and legacy `admin`) — manages one school. Logs in with school code + username.
- `teacher` — sees their own class only (the first active class assigned to them).
- Almost every table has a `school_id`. Helpers in `app/utils.py` enforce separation:
  `school_scoped_query`, `demo_filter_pupils`, `demo_filter_classes`, `require_same_school`, `current_school_id`.
  **Every new query on school data must use these or filter by `school_id` explicitly.**
- `AcademicYear` rows are shared by all schools (just the names like `2026/27`); each school points at its own one.

## How the code is laid out

```
config.py              Settings (dev/prod), DB URL tidy-up, cookie/security settings
wsgi.py / run.py       Entry points (Gunicorn uses wsgi:app)
app/__init__.py        App factory: blueprints, security headers, startup bootstraps, CLI (create-admin)
app/models/            Database tables (SQLAlchemy)
app/services/          Business logic (assessments.py is the big one; gap.py, sats_tracker.py,
                       admin_ops.py = rollover/promotion, assessment_imports.py, school_backup.py ...)
app/<area>/routes.py   Web pages: auth, dashboards, teacher, admin, pupils, executive, assessment_workflow,
                       legal, fundamentals (hidden)
app/templates/, app/static/   Jinja pages, CSS, JS (autosave, entry grids)
migrations/versions/   Alembic migrations (run automatically on each Render deploy)
tests/                 pytest suite (SQLite; one Postgres migration test and one Playwright test run in CI)
launcher/              Optional static "waking up" page for when Render is asleep (not deployed)
scripts/               Postgres backup/restore and one-off backfill scripts
```

## Running locally and tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export APP_ENV=development SECRET_KEY=dev-only
flask --app wsgi:app db upgrade
python seed.py          # fake dev data — NEVER run with DATABASE_URL pointing at the live database
python run.py           # http://localhost:8080
pytest -q --ignore=tests/test_intervention_browser.py --ignore=tests/test_intervention_migration.py
```

Without `DATABASE_URL` the app uses a local SQLite file in `instance/`. If `DATABASE_URL` is set and
`APP_ENV` isn't, the app assumes **production** — be careful which database a command points at.
CI (`.github/workflows/test.yml`) runs the full suite on every pull request.

## How it deploys (Render)

- Hosted on Render's **free** web service, deploying from the GitHub `main` branch (treat anything merged to
  `main` as going live).
- Build: `pip install -r requirements.txt && flask --app wsgi:app db upgrade` (so **migrations run against the
  live database on every deploy**). Start: `gunicorn wsgi:app --timeout 180` (one sync worker by default).
- Required env vars: `APP_ENV=production`, `SECRET_KEY` (app refuses to start in production without one),
  `DATABASE_URL` (the Supabase connection string). Optional: `DEMO_MODE`, `FUNDAMENTALS_ENABLED`,
  `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`, `LOGIN_MAX_ATTEMPTS_PER_IP`,
  `BOOTSTRAP_ADMIN_USERNAME`/`BOOTSTRAP_ADMIN_PASSWORD`.
- Free plan limits: ~512 MB RAM, sleeps after ~15 minutes idle (slow first load), no Render Shell.
  `.github/workflows/keep-awake.yml` pings `/healthz` every 10 minutes 7am–5pm UK time on weekdays
  (needs the `SITE_URL` repository variable).
- Note: `render.yaml` and parts of `README.md` still describe a paid Render Postgres setup. They do not match the
  real setup (Render free + Supabase). Don't "sync" the blueprint without checking with the owner.

## How it uses Supabase

- Supabase is used **only as a hosted PostgreSQL database**. The app connects with SQLAlchemy/psycopg2 using
  `DATABASE_URL`; `sslmode=require` is added automatically. No Supabase client library, API keys, Auth or Storage
  are used by the app.
- Free plan: the project pauses after about a week with no activity (the keep-awake job prevents this), limited
  storage and connections, and no point-in-time recovery — take manual backups with `scripts/backup_postgres.sh`
  before risky changes (see `docs/backup_restore.md`).
- Keep the database connection string out of the repo. `.env` is git-ignored.

## Conventions

- Plain-English flash messages; UK spelling.
- Add an Alembic migration for every schema change; make it safe to run on existing live data. Unique rules on
  school-owned tables must include `school_id`. Note: running every migration from an empty Postgres database
  fails on two old migrations; to test a new migration on Postgres, build tables with `db.create_all()`, stamp
  the previous revision, then upgrade.
- Write CSV exports with `app/services/safe_csv.py` (`safe_csv.writer` / `safe_csv.DictWriter`) and call
  `safe_csv.neutralise_workbook_formulas(wb)` before saving any openpyxl workbook.
- Password changes must go through `set_password` and, for the signed-in user, refresh the session stamp
  (`password_stamp` in `app/security.py`), otherwise the user is signed out on their next click.
- Pages that loop over classes or pupils must not query per row: load results in one query and group in Python.
- New school-data features need a test proving School A cannot see School B's data.
- Audit important admin actions with `log_audit_event` (`app/utils.py`).
