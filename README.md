# assessment-tracker-v2

A Phase 1 starter Flask application for a school assessment tracker covering Years 1 to 6. This first version focuses on the app foundations: authentication, dashboards, class/pupil structure, subject placeholders, admin placeholders, and a reliable setup for a shared school server PC.

## Project overview

This project provides a clean, modular Flask codebase that is ready to grow into a full assessment tracker. In this phase you can:

- sign in as an admin or teacher
- open role-based dashboards
- view a teacher class overview
- navigate to placeholder subject pages for Maths, Reading, SPaG, and Writing
- open admin placeholder pages for classes, pupils, settings, and imports
- seed the database with sample users, classes, pupils, and assessment settings

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

### 4) Initialise the database migrations

Run these commands the first time you set up the project:

```bash
flask db init
flask db migrate -m "Initial schema"
flask db upgrade
```

> Note: the repository includes a `migrations/` folder placeholder, but you still need to run the commands above locally to generate migration files for your environment.

### 5) Seed sample data

```bash
python seed.py
```

### 6) Run the application

```bash
python run.py
```

The development server starts on `http://0.0.0.0:8080/`.

## Default test logins

- Admin: `admin` / `admin1234`
- Teacher: `teacher1` / `teacher1234`

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
- The application is desktop-first but responsive enough for common laptop screens.
- The codebase uses blueprints and separate model files to keep future phases maintainable.
- Import/export, charts, SATs views, and spreadsheet editing are intentionally left as placeholders for later phases.

## Suggested Phase 2 tasks

1. Add editable assessment entry forms and validation for term-based subject scores.
2. Build CSV import/export workflows with template downloads and import previews.
3. Add writing-band editing, intervention management, and calculated dashboard summaries.
4. Create Year 6 SATs pages and term filters.
5. Add richer admin controls for class allocation, pupil management, and assessment settings.
