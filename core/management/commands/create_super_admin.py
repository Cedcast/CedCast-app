from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a Super Admin user for CedCast (non-interactive).'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='superadmin')
        parser.add_argument('--email', type=str, default='admin@example.com')
        parser.add_argument('--password', type=str, default=None)

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        email = options['email']
        password = options['password']

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists.'))
            return

        if not password:
            # generate a reasonably strong password if not provided
            import secrets
            password = secrets.token_urlsafe(12)

        user = User.objects.create_user(username=username, email=email, password=password)
        # Ensure superuser/staff flags and role are set
        user.is_staff = True
        user.is_superuser = True
        try:
            if hasattr(User, 'SUPER_ADMIN'):
                setattr(user, 'role', User.SUPER_ADMIN)
        except Exception:
            # If custom role attribute not present, ignore
            pass
        user.save()

        self.stdout.write(self.style.SUCCESS(f'Created super admin: {username}'))
        self.stdout.write(f'PASSWORD:{password}')
