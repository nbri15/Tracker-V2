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

Each teacher is linked to the matching Year 1 to Year 6 class. The admin users page also includes a **Repair default logins** action to refresh this mapping safely without requiring a reset seed.

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

Included tools:

- pupil import template download
- subject result import template download
- writing import template download
- CSV upload for pupils, subject results, and writing results
- CSV export for the main overview/reporting routes listed above

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

1. Sign in as `admin` / `admin123`.
2. Open **Users** and confirm `teacher1` to `teacher6` are linked to `Year 1` to `Year 6`.
3. Open **Year 6 SATs** and confirm the tracker mode and default SATs columns look correct.
4. Open **Promotion & history** before end-of-year testing if you want a snapshot/export first.
