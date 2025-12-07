#!/usr/bin/env bash
set -euo pipefail

# Creates a Python virtual environment in .venv and installs requirements
# Usage: ./scripts/setup_dev_env.sh [python-executable]
# Example: ./scripts/setup_dev_env.sh python3.11

PYTHON=${1:-python3}
VENV_DIR=".venv"
REQ_FILE="requirements.txt"

echo "Using Python: ${PYTHON}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python executable '$PYTHON' not found. Install Python or pass a different one." >&2
  exit 1
fi

if [ ! -f "$REQ_FILE" ]; then
  echo "Requirements file '$REQ_FILE' not found in project root." >&2
  exit 1
fi

# Create venv
if [ -d "$VENV_DIR" ]; then
  echo "Virtualenv dir '$VENV_DIR' already exists. Skipping creation." 
else
  echo "Creating virtualenv in $VENV_DIR..."
  $PYTHON -m venv "$VENV_DIR"
fi

# Activate and install
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REQ_FILE"

echo "Environment ready. Activate with: source $VENV_DIR/bin/activate"

echo "Run tests: python manage.py test --verbosity 2"
