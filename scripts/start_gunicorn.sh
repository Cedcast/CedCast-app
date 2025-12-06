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
exec gunicorn school_alert_system.wsgi:application \
  --workers "$NUM_WORKERS" \
  --bind "$BIND" \
  --log-file "$LOG_FILE" \
  --access-logfile -
