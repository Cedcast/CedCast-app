from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from core.models import Organization, Contact, OrgMessage, OrgAlertRecipient, User


class Command(BaseCommand):
    help = "Seed a demo organization with contacts and one scheduled message."

    def handle(self, *args, **options):
        name = "Demo Pharmacy"
        slug = base = slugify(name)
        i = 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        org, created = Organization.objects.get_or_create(
            name=name,
            defaults={
                'org_type': 'pharmacy',
                'slug': slug,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created organization: {org.name} ({org.slug})"))
        else:
            self.stdout.write(f"Organization exists: {org.name} ({org.slug})")

        if org.contacts.count() == 0:
            for idx in range(1, 6):
                Contact.objects.create(
                    organization=org,
                    name=f"Customer {idx}",
                    phone_number=f"+2335512345{idx:02d}",
                )
            self.stdout.write(self.style.SUCCESS("Created 5 contacts"))

        admin_user, _ = User.objects.get_or_create(
            username="orgadmin",
            defaults={"email": "orgadmin@example.com", "role": User.ORG_ADMIN}
        )
        admin_user.organization = org
        admin_user.set_password("admin123")
        admin_user.save()

        if OrgMessage.objects.filter(organization=org).count() == 0:
            msg = OrgMessage.objects.create(
                organization=org,
                content="Promo: 10% off all prescriptions this week.",
                scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
                sent=False,
                created_by=None,
            )
            for c in org.contacts.all():
                OrgAlertRecipient.objects.create(message=msg, contact=c, status='pending')
            self.stdout.write(self.style.SUCCESS("Created one scheduled org message with recipients"))

        self.stdout.write(self.style.SUCCESS("Demo organization seeding complete."))
