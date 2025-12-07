from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os


class Command(BaseCommand):
    help = "Ensure a super-admin (or admin) user exists using environment variables. Safe to run at startup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username-env",
            default="CREATE_SUPERADMIN_USERNAME",
            help="Env var name that holds the username",
        )
        parser.add_argument(
            "--email-env",
            default="CREATE_SUPERADMIN_EMAIL",
            help="Env var name that holds the email",
        )
        parser.add_argument(
            "--password-env",
            default="CREATE_SUPERADMIN_PASSWORD",
            help="Env var name that holds the password",
        )

    def handle(self, *args, **options):
        username_key = options.get("username_env")
        email_key = options.get("email_env")
        password_key = options.get("password_env")

        username = os.environ.get(username_key)
        password = os.environ.get(password_key)
        email = os.environ.get(email_key)

        if not username or not password:
            self.stdout.write(self.style.NOTICE(
                "CREATE_SUPERADMIN_USERNAME or CREATE_SUPERADMIN_PASSWORD not set — skipping ensure_superadmin"
            ))
            return

        is_super = str(os.environ.get("CREATE_SUPERADMIN_IS_SUPERUSER", "true")).lower() in ("1", "true", "yes")
        is_staff = str(os.environ.get("CREATE_SUPERADMIN_IS_STAFF", "true")).lower() in ("1", "true", "yes")

        User = get_user_model()
        try:
            user = None
            # Prefer exact username match, otherwise try email
            if username:
                user = User.objects.filter(username=username).first()
                # Ensure role is set to SUPER_ADMIN for this account when appropriate
                try:
                    if hasattr(User, 'SUPER_ADMIN') and getattr(user, 'role', None) != User.SUPER_ADMIN:
                        user.role = User.SUPER_ADMIN
                        updated = True
                except Exception:
                    # If custom user model doesn't use 'role', ignore
                    pass
            if not user and email:
                user = User.objects.filter(email=email).first()

            if user:
                updated = False
                if email and user.email != email:
                    user.email = email
                    updated = True
                if user.is_superuser != is_super:
                    user.is_superuser = is_super
                    updated = True
                if user.is_staff != is_staff:
                    user.is_staff = is_staff
                    updated = True
                    # Only overwrite the password if explicitly requested.
                    # This avoids changing the admin password on every deploy while still
                    # allowing automated resets when CREATE_SUPERADMIN_FORCE_RESET is set.
                    force_reset = str(os.environ.get("CREATE_SUPERADMIN_FORCE_RESET", "false")).lower() in ("1", "true", "yes")
                    if force_reset:
                        user.set_password(password)
                        updated = True
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated existing user '{user.username}'"))
                if updated:
                    self.stdout.write(self.style.SUCCESS("User flags/metadata updated."))
            else:
                if is_super:
                    # create_superuser may not set custom role attributes; create then ensure role
                    user = User.objects.create_superuser(username=username, email=email or "", password=password)
                    try:
                        if hasattr(User, 'SUPER_ADMIN'):
                            user.role = User.SUPER_ADMIN
                            user.save()
                    except Exception:
                        pass
                    self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'"))
                else:
                    user = User.objects.create_user(username=username, email=email or "", password=password)
                    user.is_staff = is_staff
                    user.is_superuser = is_super
                    try:
                        if hasattr(User, 'SUPER_ADMIN') and is_super:
                            user.role = User.SUPER_ADMIN
                    except Exception:
                        pass
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"Created user '{username}'"))

        except Exception as exc:  # pragma: no cover - runtime/db errors should be visible
            self.stderr.write(f"ensure_superadmin: error accessing DB or creating user: {exc}")
            # Do not raise — this keeps startup resilient in case DB isn't ready yet.
            return
