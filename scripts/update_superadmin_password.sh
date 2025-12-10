#!/usr/bin/env bash
# Update a superadmin (or any user) password using Django's ORM.
# Intended to be run inside the Render shell or any environment where
# the project's virtualenv and settings are available.
#
# Usage:
#   ./scripts/update_superadmin_password.sh username newpassword
#   ./scripts/update_superadmin_password.sh  # interactive prompt

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -z "${1-}" ]; then
  read -r -p "Username (e.g. superadmin): " USERNAME
else
  USERNAME="$1"
fi

if [ -z "${2-}" ]; then
  # do not echo password
  read -r -s -p "New password: " NEWPW
  echo
else
  NEWPW="$2"
fi

if [ -z "$USERNAME" ] || [ -z "$NEWPW" ]; then
  echo "Username and password are required" >&2
  exit 2
fi

PYCODE=$(cat <<'PY'
from django.contrib.auth import get_user_model
User = get_user_model()
username = __USERNAME__
newpw = __NEWPW__
try:
    u = User.objects.filter(username=username).first()
    if not u:
        # try email fallback
        u = User.objects.filter(email=username).first()
    if not u:
        print(f"NOUSER {username}")
    else:
        u.set_password(newpw)
        u.save()
        print(f"RESET {u.username}")
except Exception as e:
    import sys
    print(f"ERROR {e}")
    sys.exit(3)
PY
)

# Safely inject the values as Python literals
PYCODE=${PYCODE//__USERNAME__/$USER_NAME_LITERAL}
PYCODE=${PYCODE//__NEWPW__/$NEWPW_LITERAL}

# We need to construct safe Python literal replacements. Use python -c to build them.
USER_NAME_LITERAL=$(python3 - <<PY
import json,sys
print(json.dumps("$USERNAME"))
PY
)
NEWPW_LITERAL=$(python3 - <<PY
import json,sys
print(json.dumps("$NEWPW"))
PY
)

# Replace placeholders now that we have proper JSON-escaped literals
PYCODE=${PYCODE//__USERNAME__/$USER_NAME_LITERAL}
PYCODE=${PYCODE//__NEWPW__/$NEWPW_LITERAL}

python3 manage.py shell -c "$PYCODE"
