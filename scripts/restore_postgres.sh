#!/usr/bin/env bash
set -euo pipefail

backup_file="${1:-}"
if [[ -z "$backup_file" || ! -f "$backup_file" ]]; then
  echo "Usage: CONFIRM_RESTORE=YES RESTORE_DATABASE_URL=postgresql://... $0 BACKUP_FILE" >&2
  exit 1
fi
if [[ -z "${RESTORE_DATABASE_URL:-}" ]]; then
  echo "RESTORE_DATABASE_URL is required." >&2
  exit 1
fi
if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Set CONFIRM_RESTORE=YES to acknowledge that the target database will be replaced." >&2
  exit 1
fi

pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" "$backup_file"
echo "Restore completed. Run migrations and application verification before enabling access."
