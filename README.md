# assessment-tracker-v2

A Phase 3 Flask application for a school assessment tracker covering Years 1 to 6. This build keeps the teacher spreadsheet-style pages, preserves the teacher-side settings strip and existing assessment routes, and adds GAP/QLA, interventions, Year 6 SATs tracking, CSV tooling, and stronger admin management.

## Project overview

This project now supports:

- sign in as an admin or as Year 1 to Year 6 teacher users
- open role-based dashboards
- enter Maths, Reading, SPaG, and Writing results for the logged-in teacher's class
- keep teacher-editable subject settings directly on each teacher subject page
- open GAP / question analysis pages for Maths, Reading, and SPaG
- save question metadata, question-level scores, totals, and simple GAP summaries
- auto-flag the closest 6 pupils below the pass threshold for interventions
- manage intervention notes and active / inactive status
- use a real Year 6 SATs tracker with 4 assessment points plus writing judgements
- import pupils, subject results, and writing results from CSV
- download CSV templates and export assessment data back to CSV
- manage teacher users and class-to-teacher assignments from admin pages
- use richer admin class overview pages, class detail pages, intervention views, and Year 6 SATs overviews

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

### 4) Run database migrations

```bash
flask db upgrade
```

Run this once after cloning the repo and again whenever new migrations are added.

### 5) Seed development data

Normal reseed / refresh:

```bash
python seed.py
```

Optional hard reset for local development:

```bash
python seed.py --reset
```

The seed script is safe to rerun in normal local development. It now updates the documented default users in place, resets their passwords to the expected development defaults, relinks each teacher to the matching `Year 1` to `Year 6` class, and recreates the sample data without requiring manual database deletion.

Use `--reset` only when you explicitly want to wipe the current development data and rebuild the default local dataset from scratch.

### 6) Run the application

```bash
python run.py
```

The development server starts on `http://0.0.0.0:8080/`.

## Default development logins

### Admin

- `admin` / `admin123`

### Teachers

- Year 1: `teacher1` / `teacher1`
- Year 2: `teacher2` / `teacher2`
- Year 3: `teacher3` / `teacher3`
- Year 4: `teacher4` / `teacher4`
- Year 5: `teacher5` / `teacher5`
- Year 6: `teacher6` / `teacher6`

Each teacher is linked to the matching `Year 1` to `Year 6` class in the seed data.

## GAP / QLA pages

Teacher score pages for Maths, Reading, and SPaG now include a **GAP Analysis** / **Question Analysis** link.

Routes:

- `/teacher/maths/gap`
- `/teacher/reading/gap`
- `/teacher/spag/gap`

How GAP works:

- one row per pupil
- one column per question
- teachers can edit question labels such as `1`, `2`, `3a`, `3b`
- teachers can edit question type / topic and max score
- totals calculate across the row
- the page shows max total plus simple summary cards for question averages, lowest-performing questions, and weakest topics

### GAP sync rule

When GAP totals are saved:

- if a pupil has no main subject result yet for that subject / term / year, the combined score is populated from GAP and the source becomes `gap`
- if a saved manual or CSV result already exists, the app does **not** silently overwrite it
- if the GAP total differs from an existing manual or CSV result, the page shows a warning flash message

## Intervention suggestions

Teacher subject pages and the teacher interventions page use the current pass threshold from the teacher-editable settings strip.

The app:

- finds pupils below the pass threshold
- sorts them by highest score still below the threshold, so the closest pupils are prioritised
- auto-flags the closest 6 pupils
- stores intervention records with subject, term, academic year, reason, note, auto/manual state, and active state

Routes:

- `/teacher/interventions`
- `/admin/interventions`

Teachers can add extra pupils manually and mark interventions inactive when complete.

## Year 6 SATs tracker

Routes:

- `/teacher/sats`
- `/admin/sats`

The Year 6 SATs tracker includes:

- Reading, Maths, and SPaG
- 4 assessment points for raw and scaled scores
- automatic most-recent scaled score display
- writing judgements stored separately from the raw/scaled subjects
- spreadsheet-style bulk save
- admin cohort overview for Year 6

Only the Year 6 teacher meaningfully uses the teacher-facing SATs page, while admin can always view the cohort.

## CSV import / export

Admin import page:

- `/admin/imports`

Included tools:

- pupil import template download
- subject result import template download
- writing import template download
- CSV upload for pupils, subject results, and writing results
- CSV export for subject results and writing results

Import rules:

- rows are validated and reported through flash messages
- manual subject results are not silently overwritten by CSV imports
- imported subject result rows use source `csv`
- the workflow is intentionally simple and admin-friendly rather than heavily automated

## Admin management pages

Routes:

- `/admin/users`
- `/admin/classes`

Admin users can:

- create teacher users
- edit usernames
- reset passwords by entering a new password
- assign or reassign teachers to classes
- create new classes
- view class-to-teacher mapping in the main class table

## Admin overview improvements

The admin dashboard and class pages now include:

- stronger class overview links
- filters for year group, class, teacher, and pupil subgroup views (`PP`, `LAPS`, `service child`)
- sortable class overview tables
- active intervention counts by class
- class detail pages with pupil lists, subject summaries, intervention summaries, and Year 6 SATs summary blocks

## Typical development commands

### Apply migrations

```bash
flask db upgrade
```

### Seed or refresh development data

```bash
python seed.py
```

### Hard reset and reseed development data

```bash
python seed.py --reset
```

### Run the app

```bash
python run.py
```

## Recommended next Phase 4 ideas

- add a safe “use GAP total” overwrite action for manual review
- add CSV preview screens before commit
- add richer admin export filtering with downloadable subgroup summaries
- add intervention review dates and impact tracking
- add printable parent / staff reports for Year 6 SATs and term summaries
- add automated tests for service-layer logic and route workflows
