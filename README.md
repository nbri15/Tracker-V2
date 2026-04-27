# assessment-tracker-v2

A Phase 4 Flask assessment tracker for Years 1 to 6. The app keeps the existing spreadsheet-style teacher workflows, GAP/intervention/import features, teacher-side settings, and SATs work, while adding a Year 6 mode toggle, flexible SATs columns, stronger admin setup tools, promotion/history support, and broader exports.

## Project overview

The current build supports:

- role-based admin and teacher dashboards
- spreadsheet-style result entry for Maths, Reading, SPaG, and Writing
- teacher-editable subject settings on the teacher subject pages
- GAP / QLA pages for Maths, Reading, and SPaG
- intervention suggestions and manual intervention management
- Year 6 operating in either **Usual tracker** mode or **SATs tracker** mode
- flexible SATs columns with editable name, subject, max marks, pass percentage, order, and visibility
- admin SATs visibility with whole-cohort and class-level views
- admin creation/editing/archive of classes and clearer class-to-teacher mapping
- admin creation/editing of teacher users plus password resets and class reassignment
- academic-year snapshot and promotion tooling that preserves historic class membership
- CSV imports plus class, pupil, SATs, intervention, subject, writing, and history exports

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
export APP_ENV=development
export SECRET_KEY='change-this-in-production'
```

#### Windows PowerShell

```powershell
$env:FLASK_APP = 'run.py'
$env:APP_ENV = 'development'
$env:SECRET_KEY = 'change-this-in-production'
```

### 4) Run database migrations

```bash
flask db upgrade
```

Run this after cloning and whenever a new migration is added.

### 5) Seed or refresh development data

Normal refresh:

```bash
python seed.py
```

Optional hard reset:

```bash
python seed.py --reset
```

The seed refresh is safe to rerun during development. It updates the documented default users in place, resets the expected dev passwords, relinks `teacher1` to `teacher6` to `Year 1` to `Year 6`, ensures Year 6 SATs mode defaults exist, and rebuilds sample data.

### 6) Run the application

```bash
python run.py
```

The development server starts on `http://0.0.0.0:8080/`.

## Demo Mode (safe showcase mode)

Enable demo mode with:

```bash
export DEMO_MODE=true
```

When enabled, the app:

- shows a **Demo Mode** badge in the interface
- shows fake demo credentials on the login page
- supports `/demo-login` shortcuts for demo teacher/admin
- blocks destructive actions (such as delete/archive/promotion actions)

Seed fake demo data (safe to rerun and does not wipe existing data):

```bash
python seed_demo.py
```

Demo accounts:

- `demo_admin` / `demo123`
- `demo_teacher` / `demo123`

## Default local seed accounts (development only)

`seed.py` refreshes local development accounts and class links. These credentials are for local/dev use only and should never be used in production.

Each teacher is linked to the matching Year 1 to Year 6 class. The admin users page includes a **Repair default accounts** action only when `APP_ENV=development`.

## Year 6 mode toggle

Year 6 can operate in one of two modes:

- **Usual tracker**: use the normal Maths / Reading / SPaG / Writing pages like other year groups.
- **SATs tracker**: use the dedicated SATs tracker page.

Routes:

- `/teacher/sats`
- `/admin/sats`
- `/admin/classes/<class_id>/sats`

The selected Year 6 mode is stored in the database, shown on the teacher and admin SATs pages, and can be changed without affecting other year groups.

## Flexible SATs columns

When Year 6 is in SATs mode, SATs columns are loaded dynamically from the database.

Each SATs column stores:

- name
- subject
- max marks
- pass percentage
- display order
- visible / hidden status

Example columns:

- `Autumn Reading 1`
- `Autumn SPaG 1`
- `Autumn Arithmetic 1`
- `Spring Mock Reading`
- `Spring Mock SPaG`
- `Pre-SATs Arithmetic`

Teachers and admins can add new columns, hide/show them, and reorder them with display order numbers from the SATs page.

## Promotion and history workflow

Admin promotion tools live at:

- `/admin/promotion`

Workflow:

1. Use **Archive current year snapshot** to save the current pupil-to-class mapping for the selected academic year.
2. Use **Promote active pupils** to move active pupils into the next year-group class.
3. Year 6 pupils are marked inactive instead of being deleted.
4. Historical assessment data remains in place because result tables keep their academic year values.
5. Historic class placement can be reviewed on the promotion/history page or exported to CSV.

## Reporting and exports

Admin export routes now include:

- class overview CSV
- pupil overview CSV
- SATs CSV
- interventions CSV
- subject results CSV
- writing results CSV
- promotion/history CSV

Use the export buttons on the classes, SATs, and promotion pages for the most common workflows.

## Admin setup and management

Routes:

- `/admin/classes`
- `/admin/users`

Admin users can now:

- create classes
- edit class name, year group, active state, and assigned teacher
- archive classes
- create teacher users
- edit usernames
- reset passwords
- activate/deactivate logins
- assign or reassign teachers to classes
- refresh the documented default dev logins and class links safely

## CSV import / export

Admin import page:

- `/admin/imports`

Main combined import workflow:

- download the recommended combined template from the imports page
- complete one row per pupil
- required pupil columns: `first_name`, `last_name`, `gender`, `pupil_premium`, `laps`, `service_child`, `class_name`, `academic_year`
- optional subject columns: `maths_autumn_paper1`, `maths_autumn_paper2`, `maths_spring_paper1`, `maths_spring_paper2`, `maths_summer_paper1`, `maths_summer_paper2`, `reading_autumn_paper1`, `reading_autumn_paper2`, `reading_spring_paper1`, `reading_spring_paper2`, `reading_summer_paper1`, `reading_summer_paper2`, `spag_autumn_paper1`, `spag_autumn_paper2`, `spag_spring_paper1`, `spag_spring_paper2`, `spag_summer_paper1`, `spag_summer_paper2`
- optional writing columns: `writing_autumn_band`, `writing_autumn_notes`, `writing_spring_band`, `writing_spring_notes`, `writing_summer_band`, `writing_summer_notes`

Combined import behaviour:

- pupils are matched by `first_name + last_name + class_name`
- missing pupils are created automatically
- existing pupils are updated in place
- subject results are only processed when at least one score column for that subject/term is filled in
- if both score cells for a subject/term are blank, that subject result is ignored safely
- writing rows are only processed when the matching writing band column is filled in
- existing manual/protected results are not overwritten by CSV imports by default
- existing CSV results can be updated by a later CSV upload
- the import page shows counts for pupils created/updated, subject results created/updated, writing results created/updated, protected results skipped, rows skipped, and row-level validation messages

Additional supported CSV workflows:

- Reception tracker CSV import and export (from the same imports page)
- Year 6 SATs tracker CSV import and export (from the same imports page)
- CSV exports for the main overview/reporting routes listed above

## Typical development commands

### Apply migrations

```bash
flask db upgrade
```

### Refresh development data safely

```bash
python seed.py
```

### Hard reset and reseed local development data

```bash
python seed.py --reset
```

### Run the app

```bash
python run.py
```

## Manual notes after migrating

Recommended manual checks after `flask db upgrade`:

1. Sign in with your local admin account created for development.
2. Open **Users** and confirm teacher users are linked to the expected classes.
3. Open **Year 6 SATs** and confirm the tracker mode and default SATs columns look correct.
4. Open **Promotion & history** before end-of-year testing if you want a snapshot/export first.


## Render deployment (Web Service + Render Postgres)

This repository is ready for Render deployment using:

- web entrypoint: `gunicorn wsgi:app`
- DB connection from `DATABASE_URL`
- production mode via `APP_ENV=production`

### Render build command

```bash
pip install -r requirements.txt
```

### Render start command

```bash
gunicorn wsgi:app
```

### Required Render environment variables

- `APP_ENV=production`
- `SECRET_KEY=<strong-random-secret>`
- `DATABASE_URL=<Render Postgres connection string>`

Notes:
- The app uses `DATABASE_URL` when present.
- If the URL starts with `postgres://`, it is normalized to `postgresql://` automatically for SQLAlchemy compatibility.
- SQLite fallback is used only when `DATABASE_URL` is not set (local development).

### Migrations on Render

Run migrations after deploy (or via a Render one-off shell):

```bash
flask --app run.py db upgrade
```

Optional (only when schema changes are introduced locally):

```bash
flask --app run.py db migrate -m "describe change"
flask --app run.py db upgrade
```

### First admin bootstrap (production-safe)

Create the initial admin user once (does not reset DB, does not seed demo data):

```bash
flask --app run.py create-admin --username <admin_username>
```

You can also supply credentials with env vars for non-interactive use:

```bash
ADMIN_USERNAME=<admin_username> ADMIN_PASSWORD='<strong-password>' flask --app run.py create-admin
```

Behaviour:
- command is a no-op if an admin already exists
- requires password length of at least 8
- does not run `seed.py`

### Render blueprint

A `render.yaml` blueprint is included to provision:
- one Python web service
- one Render Postgres database
- environment variable wiring for `DATABASE_URL`

### Local vs production

- Local development: `APP_ENV=development`, SQLite fallback, optional `seed.py`.
- Production: `APP_ENV=production`, Postgres via `DATABASE_URL`, secure cookies enabled, no development account bootstrap UI.
