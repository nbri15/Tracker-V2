# assessment-tracker-v2

A Phase 2 Flask application for a school assessment tracker covering Years 1 to 6. This version adds working spreadsheet-style assessment entry for teachers, editable assessment settings for admins, real dashboard summaries, and seeded sample data that shows live counts immediately after setup.

## Project overview

This project now supports:

- sign in as an admin or teacher
- open role-based dashboards
- enter Maths, Reading, SPaG, and Writing results for the logged-in teacher's class
- switch by academic year and term
- bulk-save and reload spreadsheet-style assessment tables
- auto-calculate combined scores, percentages, and category bands for score-based subjects
- manage editable assessment settings for every year group, subject, and term
- view teacher dashboard summary cards and tables based on real saved data
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

This repository now includes migration files. For a normal setup run:

```bash
flask db upgrade
```

If you already have a local Phase 1 SQLite database from before migration files were added, back it up first. In many local-dev cases the simplest reset path is:

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
- sample subject and writing results for the teacher class so the dashboard shows live data immediately

### 6) Run the application

```bash
python run.py
```

The development server starts on `http://0.0.0.0:8080/`.

## Default test logins

- Admin: `admin` / `admin1234`
- Teacher: `teacher1` / `teacher1234`

## How assessment settings work

Admins manage settings on `/admin/settings`.

Each setting row is scoped by:

- year group
- subject
- term

For Maths, Reading, and SPaG each row stores:

- paper names
- paper max scores
- combined max score
- threshold percentages

If `combined_max` is left blank in the add/update form, it auto-fills from `paper_1_max + paper_2_max`.

### Category logic

For score-based subjects, the app uses the saved thresholds for the selected year group, subject, and term.

- if percent is below `below_are_threshold_percent` → `Working Towards`
- if percent is greater than or equal to `below_are_threshold_percent` and below `exceeding_threshold_percent` → `On Track`
- if percent is greater than or equal to `exceeding_threshold_percent` → `Exceeding`

`On Track+` is a dashboard summary measure only. It is calculated as `On Track + Exceeding` and is not stored as a per-pupil band.

## How teachers enter results

Teachers enter data from the subject pages:

- `/teacher/maths`
- `/teacher/reading`
- `/teacher/spag`
- `/teacher/writing`

### Maths, Reading, and SPaG

On each page the teacher can:

- select academic year and term
- search pupils
- sort by pupil name or combined percent
- enter paper scores and optional notes in one table
- save all visible rows in bulk

The app then:

- validates scores against the current max scores
- saves source as `manual`
- recalculates combined score and percent
- rounds percentages to 1 decimal place
- recalculates the band label from the current setting

### Writing

The Writing page supports:

- academic year and term switching
- one row per pupil
- a writing band dropdown
- optional notes
- bulk save and reload

Dashboard summaries map writing bands like this:

- `Working Towards` → Working Towards
- `Expected` → On Track
- `Greater Depth` → Exceeding

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

## Recommended exact Phase 3 tasks

1. Build CSV import with downloadable templates, preview validation, and row-level error reporting.
2. Add GAP sync placeholders into a real sync workflow with source tracking and conflict handling.
3. Add QLA and question-level breakdown storage for Maths, Reading, and SPaG.
4. Add intervention suggestion logic that reads saved attainment bands without auto-applying changes.
5. Build admin whole-school analytics with year-group summaries, filters, and export-ready tables.
6. Add Year 6 SATs entry pages, scaled-score summaries, and dashboard cards.
7. Add audit history and change timestamps to assessment edits for admin review.
