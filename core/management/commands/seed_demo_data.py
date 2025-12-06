from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import School, Parent, Ward, Message, AlertRecipient
from django.utils.text import slugify


class Command(BaseCommand):
    help = "Seed demo data: superuser, demo school, school admin, parents/wards, and a scheduled message."

    def handle(self, *args, **options):
        User = get_user_model()

        # Create superuser if not exists
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(username="admin", password="admin123", email="admin@example.com", role=User.SUPER_ADMIN)
            self.stdout.write(self.style.SUCCESS("Created superuser admin / admin123 (dev only)"))
        else:
            self.stdout.write("Superuser 'admin' already exists")

        # Create demo school
        school_name = "Demo School"
        base_slug = slugify(school_name)
        slug = base_slug
        i = 2
        while School.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{i}"
            i += 1

        school, created = School.objects.get_or_create(
            name=school_name,
            defaults={
                "primary_color": "#0d6efd",
                "secondary_color": "#6c757d",
                "slug": slug,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created school: {school.name} (slug={school.slug})"))
        else:
            self.stdout.write(f"School already exists: {school.name} (slug={school.slug})")

        # Create school admin
        if not User.objects.filter(username="schooladmin").exists():
            admin_user = User.objects.create_user(
                username="schooladmin",
                password="admin123",
                email="schooladmin@example.com",
                role=User.SCHOOL_ADMIN,
                school=school,
            )
            self.stdout.write(self.style.SUCCESS("Created school admin: schooladmin / admin123"))
        else:
            admin_user = User.objects.get(username="schooladmin")
            self.stdout.write("School admin 'schooladmin' already exists")

        # Create parents and wards
        if Parent.objects.filter(school=school).count() == 0:
            for idx in range(1, 6):
                parent = Parent.objects.create(
                    school=school,
                    name=f"Parent {idx}",
                    phone_number=f"+2335012345{idx:02d}",
                )
                Ward.objects.create(
                    school=school,
                    parent=parent,
                    name=f"Student {idx}",
                    student_class="JHS3" if idx % 2 == 0 else "JHS2",
                )
            self.stdout.write(self.style.SUCCESS("Created 5 parents and wards"))
        else:
            self.stdout.write("Parents already exist for demo school")

        # Create a scheduled message for immediate sending
        if Message.objects.filter(school=school).count() == 0:
            msg = Message.objects.create(
                school=school,
                content="Reminder: PTA meeting tomorrow at 10 AM.",
                scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
                sent=False,
                created_by=admin_user,
            )
            for parent in Parent.objects.filter(school=school):
                AlertRecipient.objects.create(message=msg, parent=parent, status='pending')
            self.stdout.write(self.style.SUCCESS("Created one scheduled message with recipients"))
        else:
            self.stdout.write("Messages already present; skipping message creation")

        self.stdout.write(self.style.SUCCESS("Demo data seeding complete."))
