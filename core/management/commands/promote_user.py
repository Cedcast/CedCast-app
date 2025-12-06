from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Promote a user to super admin role (and optionally Django superuser)."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to promote')
        parser.add_argument('--django-superuser', action='store_true', help='Also set is_staff and is_superuser')

    def handle(self, *args, **options):
        username = options['username']
        make_django_superuser = options['django-superuser']
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")

        # Set app-level role
        user.role = getattr(User, 'SUPER_ADMIN', 'super_admin')
        if make_django_superuser:
            user.is_staff = True
            user.is_superuser = True
        user.save()

        msg = f"User '{username}' promoted to role=super_admin."
        if make_django_superuser:
            msg += " Also granted Django superuser/staff."
        self.stdout.write(self.style.SUCCESS(msg))
