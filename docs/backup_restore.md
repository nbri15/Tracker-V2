# Production database backup and restore

## How backups work now

Production data is backed up **automatically every day** by the separate private
repository **`nbri15/class-compass-backups`** (GitHub Actions, "Daily encrypted
database backup"). Backups are encrypted with GPG AES-256, kept as private
artifacts for 30 days, and never stored in this repository. Because GitHub can
delay scheduled runs, the backup usually completes between about 08:30 and 10:00 UTC.

That repository's `README.md` is the authoritative guide for how the backup works,
the secrets it needs, and the **restore drill**. Do not rely on backups until a
drill has passed (see `drill/DRILL_LOG.md` in that repository).

## Before every deployment that includes a migration

Render runs `flask db upgrade` on each deploy. Before merging a pull request that
adds or changes a migration, academic-year promotion code, bulk deletion, or
data-changing import:

1. Open `class-compass-backups` → Actions → **Daily encrypted database backup** → Run workflow.
2. Wait for a green tick. If it fails, do **not** deploy.
3. Merge and deploy.

## Manual backup (optional, ad hoc)

`scripts/backup_postgres.sh` makes an **unencrypted** dump. Use it only for a
short-lived local copy; delete it afterwards and never commit it. It does not
replace the automatic encrypted backups.

```bash
export DATABASE_URL='postgresql://...'   # keep in the environment, never in files
./scripts/backup_postgres.sh ./backups
```

## Test a restore (isolated database only)

Preferred: use the drill in the backup repository (`drill/restore_drill.sh`),
which verifies the file, decrypts it and restores into a new local database.

`scripts/restore_postgres.sh` restores an unencrypted dump and **wipes its
target**. It refuses to run unless all of these hold: the target is not the same
database as `DATABASE_URL` or `SUPABASE_DB_URL`; the host is local (or
`ALLOW_REMOTE_RESTORE=YES` for a dedicated test server); the database name does
not contain `prod` or `live`; and you type the target database name yourself.

```bash
RESTORE_DATABASE_URL='postgresql://user:pass@localhost:5432/test_db' \
CONFIRM_RESTORE=YES CONFIRM_DB_NAME=test_db \
./scripts/restore_postgres.sh ./backups/class_compass_YYYYMMDD_HHMMSS.dump
```

After restoring, log in to a copy of the app and check schools, users, classes,
pupils, assessment results, gap analysis, interventions, SATs and Maths Fundamentals.

## Production recovery

Production recovery needs a reviewed plan and explicit approval; it is not automated.

1. Put the application into maintenance mode or stop web workers.
2. Take a final backup of the damaged database if it is still accessible.
3. Create a new empty database rather than overwriting the existing one.
4. Restore the selected, verified backup into the new database.
5. Point `DATABASE_URL` at the restored database and deploy the same application revision that created it.
6. Run migrations, perform the verification checks above, then reopen access.

Never test a restore against the live database.
