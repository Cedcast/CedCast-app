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
# Run migrations and (optionally) create/update a superadmin from env vars before starting gunicorn.
# This is safe to run on every boot; it will be a no-op if there are no migrations or the env vars are not set.
python manage.py migrate --noinput || true
# Ensure superadmin if env vars provided. The management command will skip if vars are missing.
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
