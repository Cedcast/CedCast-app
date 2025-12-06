#!/usr/bin/env bash
set -euo pipefail
# start_gunicorn.sh
# Simple wrapper to start gunicorn for this Django project.
# Usage:
#   ./scripts/start_gunicorn.sh
# Environment variables (optional):
#   GUNICORN_WORKERS - number of workers (default: 3)
#   GUNICORN_BIND - bind address (default: 0.0.0.0:8000)
#   GUNICORN_LOG_FILE - log file (default: - for stdout)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Activate virtualenv if present
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.venv/bin/activate"
elif [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/venv/bin/activate"
fi

NUM_WORKERS="${GUNICORN_WORKERS:-3}"
BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
LOG_FILE="${GUNICORN_LOG_FILE:--}"

export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-school_alert_system.settings}

echo "Starting gunicorn: bind=$BIND workers=$NUM_WORKERS"
echo "Running DB migrations (if any) and ensuring superadmin from env vars..."
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "DIAG_DB=${DIAG_DB:-<not-set>}"
# Optional diagnostic hook: set DIAG_DB=true in the environment to print
# `showmigrations core`, the django_migrations rows for core, and the
# current public tables. This helps debug migration bookkeeping when you
# don't have a shell on the host (e.g. Render free tier). The block is
# opt-in and will not run unless DIAG_DB=true.
if [ "${DIAG_DB:-}" = "true" ]; then
  echo "DIAG_DB=true: printing migration state and table listing..."
  python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
import django
django.setup()
from django.core.management import call_command
from django.db import connection
import sys
sys.stdout.write("=== showmigrations core ===\n")
call_command('showmigrations', 'core')
with connection.cursor() as cur:
    cur.execute("SELECT name, applied FROM django_migrations WHERE app='core' ORDER BY id")
    rows = cur.fetchall()
    sys.stdout.write(f"django_migrations (core): {rows}\n")
    cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
    tables = [r[0] for r in cur.fetchall()]
    sys.stdout.write(f"public tables: {tables}\n")
PY
  echo "DIAG_DB block complete."
fi

# Optional automatic repair hook. This is DANGEROUS if used without a backup.
# It will run only when REPAIR_DB=true. Behavior:
# - Try a best-effort pg_dump to /tmp/db-backup.dump (if pg_dump exists and DATABASE_URL is set)
# - Check if `core_user` table is missing but `django_migrations` contains core entries
# - If so, delete `django_migrations` rows for app 'core' so `manage.py migrate` will recreate tables
# Use this ONLY if you understand the risk and have a backup. This is opt-in.
if [ "${REPAIR_DB:-}" = "true" ]; then
  echo "REPAIR_DB=true: attempting safe repair (best-effort)."
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "REPAIR_DB requested but DATABASE_URL is not set — aborting repair."
  else
    if command -v pg_dump >/dev/null 2>&1; then
      echo "pg_dump found — attempting backup to /tmp/db-backup.dump (pg_dump --dbname=DATABASE_URL)."
      if pg_dump --dbname="$DATABASE_URL" -Fc -f /tmp/db-backup.dump; then
        echo "pg_dump completed and wrote /tmp/db-backup.dump"
      else
        echo "pg_dump failed or is not permitted in this environment — continuing cautiously"
      fi
    else
      echo "pg_dump not available in the runtime; skipping pg_dump backup"
    fi

    echo "Inspecting DB for missing core tables and migration bookkeeping..."
    python - <<'PY'
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cur:
    cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
    tables = [r[0] for r in cur.fetchall()]
    core_user_exists = 'core_user' in tables
    cur.execute("SELECT count(*) FROM django_migrations WHERE app='core'")
    mig_count = cur.fetchone()[0]
    sys.stdout.write(f"public tables: {tables}\n")
    sys.stdout.write(f"core_user exists: {core_user_exists}\n")
    sys.stdout.write(f"django_migrations (core) count: {mig_count}\n")
    # If core_user is missing but migrations claim core applied, remove core rows so migrate can recreate
    if (not core_user_exists) and mig_count > 0:
        sys.stdout.write("Detected mismatch: core migrations applied but core_user table missing. Will delete core rows from django_migrations to allow migrate to recreate tables.\n")
        cur.execute("DELETE FROM django_migrations WHERE app = 'core'")
        sys.stdout.write("Deleted django_migrations rows for app 'core'.\n")
    else:
        sys.stdout.write("No repair action required.\n")
PY
  fi
  echo "REPAIR_DB block complete."
fi
# Run migrations and (optionally) create/update a superadmin from env vars before starting gunicorn.
# On production we want migration failures to be visible in the logs so they can be addressed.
# Do not swallow migration errors; allow the process to fail so Render will show the error.
python manage.py migrate --noinput --verbosity 2
# Ensure superadmin if env vars provided. The management command will skip if vars are missing.
# keep ensure_superadmin non-fatal so a misconfigured admin env doesn't block startup
python manage.py ensure_superadmin || true

# Optional one-time import of dump.json (useful on hosts without a shell like Render free tier).
# To trigger: set IMPORT_DUMP=true and ensure DATABASE_URL is set in the environment. The script
# will import dump.json once and create a marker file `.dump_imported` to avoid re-importing.
if [ "${IMPORT_DUMP:-}" = "true" ]; then
  MARKER_FILE="$PROJECT_ROOT/.dump_imported"
  if [ -f "$PROJECT_ROOT/dump.json" ] && [ ! -f "$MARKER_FILE" ]; then
    echo "IMPORT_DUMP=true detected and dump.json found — importing fixture into DB..."
    # run loaddata but continue on error to avoid blocking startup
    python manage.py loaddata dump.json || echo "loaddata returned non-zero; continuing"
    # create marker so we don't import again
    touch "$MARKER_FILE"
    echo "Import complete; marker file created at $MARKER_FILE"
  else
    echo "IMPORT_DUMP requested but either dump.json is missing or marker exists — skipping import"
  fi
fi

exec gunicorn school_alert_system.wsgi:application \
  --workers "$NUM_WORKERS" \
  --bind "$BIND" \
  --log-file "$LOG_FILE" \
  --access-logfile -
