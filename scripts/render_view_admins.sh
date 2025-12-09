#!/usr/bin/env bash
# Run this inside your Render shell (or any environment where Django is installed and the project's settings are available).
#
# Usage:
#   ./scripts/render_view_admins.sh            # show superadmins and org admins
#   ./scripts/render_view_admins.sh --reset username1,username2  # reset listed users' passwords and print the new password
#   ./scripts/render_view_admins.sh --reset-all  # reset passwords for all superadmins and org admins (careful)
#
# This script does NOT print existing passwords (they are hashed). When resetting, it sets a random temporary password
# and prints it so you can share it securely with the user.

set -euo pipefail

USAGE="Usage: $0 [--reset user1,user2] [--reset-all]"

RESET_USERS=""
RESET_ALL=0

if [ "$#" -gt 0 ]; then
  case "$1" in
    --reset)
      if [ -z "${2-}" ]; then
        echo "$USAGE" >&2
        exit 2
      fi
      RESET_USERS="$2"
      ;;
    --reset-all)
      RESET_ALL=1
      ;;
    *)
      echo "$USAGE" >&2
      exit 2
      ;;
  esac
fi

# Prepare Python code to run under manage.py shell -c
PYCODE=$(cat <<'PY'
from django.contrib.auth import get_user_model
import secrets
User = get_user_model()

def fmt(u):
    role = getattr(u, 'role', getattr(u, 'get_role_display', lambda: None)())
    org = getattr(u, 'organization', None)
    org_slug = org.slug if org else ''
    print(f"{u.username}\t{u.email}\trole={getattr(u,'role',None)}\torg={org_slug}\tlast_login={u.last_login}\tdate_joined={u.date_joined}\tis_active={u.is_active}")

print('=== Super Admins ===')
qs = User.objects.filter(role=User.SUPER_ADMIN)
if not qs.exists():
    # fallback to is_superuser boolean
    qs = User.objects.filter(is_superuser=True)
for u in qs:
    fmt(u)

print('\n=== Organization Admins ===')
for u in User.objects.filter(role=User.ORG_ADMIN).select_related('organization'):
    fmt(u)

# handle resets injected below
RESET_USERS = __RESET_USERS__
RESET_ALL = __RESET_ALL__
if RESET_ALL:
    candidates = list(set(list(User.objects.filter(role=User.SUPER_ADMIN)) + list(User.objects.filter(role=User.ORG_ADMIN))))
    for u in candidates:
        newpw = secrets.token_urlsafe(9)
        u.set_password(newpw)
        u.save()
        print(f"RESET {u.username} -> {newpw}")
elif RESET_USERS:
    for username in RESET_USERS:
        try:
            u = User.objects.get(username=username)
            newpw = secrets.token_urlsafe(9)
            u.set_password(newpw)
            u.save()
            print(f"RESET {u.username} -> {newpw}")
        except User.DoesNotExist:
            print(f"NOUSER {username}")

PY
)

# Inject reset params
if [ "$RESET_ALL" -eq 1 ]; then
  PYCODE=${PYCODE//__RESET_USERS__/[]}
  PYCODE=${PYCODE//__RESET_ALL__/True}
else
  if [ -n "$RESET_USERS" ]; then
    # convert comma list to Python list of strings
    IFS=',' read -r -a arr <<< "$RESET_USERS"
    pylist="["
    first=1
    for v in "${arr[@]}"; do
      if [ $first -eq 1 ]; then
        pylist+=$(printf "%s" "'%s'" "$v")
        first=0
      else
        pylist+=","$(printf "%s" "'%s'" "$v")
      fi
    done
    pylist+="]"
    PYCODE=${PYCODE//__RESET_USERS__/$pylist}
    PYCODE=${PYCODE//__RESET_ALL__/False}
  else
    PYCODE=${PYCODE//__RESET_USERS__/[]}
    PYCODE=${PYCODE//__RESET_ALL__/False}
  fi
fi

# Run under Django manage.py shell
python3 manage.py shell -c "$PYCODE"
