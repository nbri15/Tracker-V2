#!/usr/bin/env bash
# Restore a Class Compass pg_dump archive into an ISOLATED test database.
#
# This script WIPES the target database (pg_restore --clean). It therefore
# refuses to run unless every safety check below passes. It is for restore
# drills only, never for the live database.
set -euo pipefail

backup_file="${1:-}"
if [[ -z "$backup_file" || ! -f "$backup_file" ]]; then
  cat >&2 <<'USAGE'
Usage:
  RESTORE_DATABASE_URL=postgresql://user:pass@localhost:5432/test_db \
  CONFIRM_RESTORE=YES CONFIRM_DB_NAME=test_db \
  ./scripts/restore_postgres.sh BACKUP_FILE.dump
USAGE
  exit 1
fi
if [[ -z "${RESTORE_DATABASE_URL:-}" ]]; then
  echo "RESTORE_DATABASE_URL is required." >&2
  exit 1
fi
if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Set CONFIRM_RESTORE=YES to acknowledge that the target database will be wiped." >&2
  exit 1
fi

# Parse the target without printing credentials.
read -r target_host target_port target_db < <(python3 -I - "$RESTORE_DATABASE_URL" <<'PY'
import sys
from urllib.parse import urlsplit
u = urlsplit(sys.argv[1])
print((u.hostname or "").lower(), u.port or 5432, u.path.lstrip("/"))
PY
)

if [[ -z "$target_host" || -z "$target_db" ]]; then
  echo "RESTORE_DATABASE_URL must include a host and a database name." >&2
  exit 1
fi

# 1. Never the production database, however the URL is written.
for production_var in DATABASE_URL SUPABASE_DB_URL; do
  production_url="${!production_var:-}"
  if [[ -n "$production_url" ]]; then
    read -r prod_host prod_port prod_db < <(python3 -I - "$production_url" <<'PY'
import sys
from urllib.parse import urlsplit
u = urlsplit(sys.argv[1])
print((u.hostname or "").lower(), u.port or 5432, u.path.lstrip("/"))
PY
)
    if [[ "$target_host" == "$prod_host" && "$target_db" == "$prod_db" ]]; then
      echo "Refusing: RESTORE_DATABASE_URL points at the same database as $production_var." >&2
      exit 1
    fi
  fi
done

# 2. Only local databases by default; hosted ones need an explicit override.
case "$target_host" in
  localhost|127.0.0.1|::1) ;;
  *)
    if [[ "${ALLOW_REMOTE_RESTORE:-}" != "YES" ]]; then
      echo "Refusing: target host '$target_host' is not local. For a dedicated, isolated" >&2
      echo "test database elsewhere, also set ALLOW_REMOTE_RESTORE=YES." >&2
      exit 1
    fi
    ;;
esac

# 3. Refuse names that look like the live database.
case "$target_db" in
  *prod*|*live*)
    echo "Refusing: database name '$target_db' looks like production." >&2
    exit 1
    ;;
esac

# 4. The operator must type the target database name.
if [[ "${CONFIRM_DB_NAME:-}" != "$target_db" ]]; then
  echo "Set CONFIRM_DB_NAME=$target_db to confirm the database that will be wiped." >&2
  exit 1
fi

echo "Restoring into database '$target_db' on '$target_host'..."
pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl \
  --dbname="$RESTORE_DATABASE_URL" "$backup_file"
echo "Restore completed. Run migrations and application verification before enabling access."
