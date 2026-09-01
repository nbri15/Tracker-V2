# Production database backup and restore

Class Compass production data should be backed up before deployments that run migrations, academic-year promotion, bulk imports, or permanent deletion.

## Create a backup

Use the PostgreSQL connection string supplied by the hosting provider. Keep it in an environment variable; do not paste credentials into scripts or commit them.

```bash
export DATABASE_URL='postgresql://...'
./scripts/backup_postgres.sh ./backups
```

The script creates a dated custom-format PostgreSQL dump and checks that the archive can be read. Store a copy outside the application host with restricted access.

## Test a restore

Restore into a separate empty PostgreSQL database first:

```bash
export RESTORE_DATABASE_URL='postgresql://...test-database...'
CONFIRM_RESTORE=YES ./scripts/restore_postgres.sh ./backups/class_compass_YYYYMMDD_HHMMSS.dump
```

Log into the restored application and verify schools, users, classes, pupils, assessment results, interventions, SATs, and Maths Fundamentals before treating the backup as valid.

## Production recovery

1. Put the application into maintenance mode or stop web workers.
2. Take a final backup of the damaged database if it remains accessible.
3. Create a new empty database rather than overwriting the existing database immediately.
4. Restore the selected verified archive into the new database.
5. point `DATABASE_URL` at the restored database and deploy the same application revision that created it.
6. Run migrations, perform the verification checks above, then reopen access.

Never test a restore against the live database.
