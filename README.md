# assessment-tracker-v2

A Phase 2.5 Flask application for a school assessment tracker covering Years 1 to 6. This version keeps the teacher spreadsheet-style pages in place, moves routine score-setting edits onto the teacher subject pages, and upgrades the admin dashboard into a practical class overview area.

## Project overview

This project now supports:

- sign in as an admin or teacher
- open role-based dashboards
- enter Maths, Reading, SPaG, and Writing results for the logged-in teacher's class
- switch by academic year and term
- bulk-save and reload spreadsheet-style assessment tables
- edit score-based assessment settings directly from each teacher subject page
- auto-calculate combined scores, percentages, and category bands for score-based subjects
- use an admin dashboard with class overview tables, filters, and subject summary cards
- open admin class detail pages with pupil lists and recent subject tables
- keep an admin-only fallback settings page for exceptional edits
- seed sample users, classes, pupils, settings, and example outcomes

## Tech stack

- Python
- Flask
- SQLite
- SQLAlchemy
- Flask-Login
- Flask-WTF
- Flask-Migrate
- Bootstrap 5
- Jinja templates

## Setup instructions

### 1) Create and activate a virtual environment

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Set environment variables

#### macOS / Linux

```bash
export FLASK_APP=run.py
export FLASK_ENV=development
export SECRET_KEY='change-this-in-production'
```

#### Windows PowerShell

```powershell
$env:FLASK_APP = 'run.py'
$env:FLASK_ENV = 'development'
$env:SECRET_KEY = 'change-this-in-production'
```

If `SECRET_KEY` is not set, the app falls back to a development-only key for local testing.

### 4) Run database migrations

This repository includes migration files. For a normal setup run:

```bash
flask db upgrade
```

If you already have a local SQLite database from before migration files were added, back it up first. In many local-dev cases the simplest reset path is:

```bash
rm -f instance/assessment_tracker.db
flask db upgrade
```

### 5) Seed sample data

```bash
python seed.py
```

The seed script creates:

- default admin and teacher accounts
- sample Year 3 and Year 6 classes
- sample pupils
- editable assessment settings for Years 1 to 6 across Maths, Reading, and SPaG for Autumn, Spring, and Summer
- sample subject and writing results for the teacher class so the dashboards show live data immediately

### 6) Run the application

```bash
python run.py
```

The development server starts on `http://0.0.0.0:8080/`.

## Default test logins

- Admin: `admin` / `admin1234`
- Teacher: `teacher1` / `teacher1234`

## How teacher subject-page settings now work

Routine setup for score-based subjects now happens on:

- `/teacher/maths`
- `/teacher/reading`
- `/teacher/spag`

Each page has a compact settings strip above the spreadsheet table for the selected:

- year group
- subject
- term

Teachers can edit and save:

- paper 1 name
- paper 1 max
- paper 2 name
- paper 2 max
- combined max
- Working Towards threshold percent
- Exceeding threshold percent

### Combined max behaviour

- By default, combined max follows `paper_1_max + paper_2_max`.
- Teachers can manually override the combined max from the subject page when needed.
- Saving settings updates the `AssessmentSetting` row for that year group, subject, and term.
- If a setting does not exist yet, the app creates it automatically.

### Category logic

For Maths, Reading, and SPaG the saved thresholds use this banding logic:

- if percent is below `below_are_threshold_percent` → `Working Towards`
- if percent is greater than or equal to `below_are_threshold_percent` and below `exceeding_threshold_percent` → `On Track`
- if percent is greater than or equal to `exceeding_threshold_percent` → `Exceeding`

`On Track+` is a summary measure only. It is calculated as `On Track + Exceeding` and is not stored as a separate pupil band.

### Recalculation after settings changes

When a teacher saves settings from a subject page, the app:

- keeps the original paper scores unchanged
- recalculates derived combined scores, percentages, and band labels for saved results in that class, subject, academic year, and term
- refreshes the page so the spreadsheet table reflects the updated settings immediately

## How teachers enter results

Teachers enter data from these pages:

- `/teacher/maths`
- `/teacher/reading`
- `/teacher/spag`
- `/teacher/writing`

### Maths, Reading, and SPaG

On each page the teacher can:

- select academic year and term
- search pupils
- sort by pupil name or combined percent
- edit settings in the compact strip at the top
- enter paper scores and optional notes in one table
- save settings separately from pupil scores
- save all visible pupil rows in bulk

The app then:

- validates scores against the current max scores
- saves source as `manual`
- recalculates combined score and percent
- rounds percentages to 1 decimal place
- recalculates the band label from the current setting

### Writing

The Writing page remains intentionally simpler. It supports:

- academic year and term switching
- one row per pupil
- a writing band dropdown
- optional notes
- bulk save and reload

No threshold settings are shown on Writing.

Dashboard summaries map writing bands like this:

- `Working Towards` → Working Towards
- `Expected` → On Track
- `Greater Depth` → Exceeding

## How admin dashboard summaries are calculated

The admin dashboard is now an overview page instead of a setup-first page.

It includes:

- whole-school headline counts
- class overview filters for academic year, year group, class, and teacher
- subject summary cards
- a class overview table
- links into `/admin/classes/<class_id>` detail pages

### Class overview summary rules

For each class and each subject, the dashboard uses the most recent term with saved data in the selected academic year.

For Maths, Reading, and SPaG it counts saved pupil bands:

- `Working Towards`
- `On Track`
- `Exceeding`
- `On Track+ = On Track + Exceeding`

For Writing it maps bands like this:

- `Working Towards` → Working Towards
- `Expected` → On Track
- `Greater Depth` → Exceeding
- `On Track+ = Expected + Greater Depth`

## Admin settings page

`/admin/settings` still exists, but it is now an advanced admin-only fallback editor rather than the main workflow.

Use it for:

- reviewing saved settings
- fixing exceptional rows
- creating or editing missing settings without using a teacher page

## Rerunning seed data

To refresh local sample data after resetting the database:

```bash
flask db upgrade
python seed.py
```

If you want a completely clean local reset first:

```bash
rm -f instance/assessment_tracker.db
flask db upgrade
python seed.py
```

## Project structure summary

```text
assessment-tracker-v2/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── utils.py
│   ├── admin/
│   ├── auth/
│   ├── dashboards/
│   ├── models/
│   ├── services/
│   ├── static/
│   ├── teacher/
│   └── templates/
├── instance/
├── migrations/
├── config.py
├── run.py
├── seed.py
├── requirements.txt
└── README.md
```

## Notes for shared-school deployment

- SQLite keeps the setup simple for a single shared school server PC.
- The application is desktop-first and optimized for quick spreadsheet-style entry.
- The codebase uses blueprints, separate model files, and service helpers to support later CSV import and sync work.
- CSV import, GAP sync, interventions automation, Year 6 SATs workflows, and whole-school analytics remain out of scope for this phase.

## Recommended next phase tasks

1. Add CSV import with downloadable templates, preview validation, and row-level error reporting.
2. Add lightweight class trend views by term without introducing heavy charting dependencies.
3. Add richer admin class drill-down pages for pupil groups, notes review, and moderation checks.
4. Add safe exports for teacher and admin overview pages.
