import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Organization, User


class Command(BaseCommand):
    help = "Ensure deploy users (superadmin and org admins) exist with known passwords; idempotent for Render deployments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-slug",
            dest="org_slug",
            default=os.environ.get("DEFAULT_ORG_SLUG", "packnet"),
            help="Organization slug to ensure (default from DEFAULT_ORG_SLUG env or 'packnet').",
        )
        parser.add_argument(
            "--super-username",
            dest="super_username",
            default=os.environ.get("SUPERADMIN_USERNAME", "superadmin"),
            help="Superadmin username.",
        )
        parser.add_argument(
            "--super-password",
            dest="super_password",
            default=os.environ.get("SUPERADMIN_PASSWORD", "Packnet#ChangeMe1"),
            help="Superadmin password.",
        )
        parser.add_argument(
            "--org-username",
            dest="org_username",
            default=os.environ.get("ORGADMIN_USERNAME", "packnet_admin"),
            help="Org admin username.",
        )
        parser.add_argument(
            "--org-password",
            dest="org_password",
            default=os.environ.get("ORGADMIN_PASSWORD", "Packnet#ChangeMe1"),
            help="Org admin password.",
        )

    def handle(self, *args, **options):
        import os
        User = get_user_model()

        org_slug = options["org_slug"]
        super_username = options["super_username"]
        super_password = options["super_password"]
        org_username = options["org_username"]
        org_password = options["org_password"]

        # Ensure organization exists
        org, _ = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={
                "name": org_slug.capitalize(),
                "org_type": "company",
            },
        )

        # Ensure superadmin
        super_user, created_super = User.objects.get_or_create(
            username=super_username,
            defaults={
                "role": User.SUPER_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "email": f"{super_username}@cedcast.com",
            },
        )
        if created_super:
            self.stdout.write(self.style.SUCCESS(f"Created superadmin '{super_username}'"))
        # Only set the password when the user was just created, or when a deploy
        # operator explicitly forces a password reset via env var.
        force_reset = os.environ.get('FORCE_DEPLOY_USER_PASSWORD', 'false').lower() in ('1', 'true', 'yes')
        if created_super or force_reset:
            if super_password:
                super_user.set_password(super_password)
                super_user.save()
                self.stdout.write(self.style.SUCCESS(f"Set password for superadmin '{super_username}' (created or forced)"))
        else:
            # Do not overwrite existing password on every deploy
            self.stdout.write(self.style.NOTICE(f"Superadmin '{super_username}' exists; password unchanged"))

        # Ensure org admin
        org_admin, created_org = User.objects.get_or_create(
            username=org_username,
            defaults={
                "role": User.ORG_ADMIN,
                "is_staff": False,
                "email": f"{org_username}@cedcast.com",
            },
        )
        # Attach to organization
        org_admin.organization = org
        # Only set org admin password on creation or when forced
        if created_org:
            if org_password:
                org_admin.set_password(org_password)
        else:
            if force_reset and org_password:
                org_admin.set_password(org_password)
        org_admin.save()
        if created_org:
            self.stdout.write(self.style.SUCCESS(f"Created org admin '{org_username}' for '{org_slug}'"))
        else:
            if force_reset:
                self.stdout.write(self.style.SUCCESS(f"Updated password for org admin '{org_username}' (forced)"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Ensured org admin '{org_username}' exists for '{org_slug}'"))

        self.stdout.write(self.style.SUCCESS("Deploy users ensured successfully."))
