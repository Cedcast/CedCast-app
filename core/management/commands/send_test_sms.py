from django.core.management.base import BaseCommand, CommandError

from core.hubtel_utils import send_sms
from core.models import School, Message, AlertRecipient, Parent
from django.utils import timezone


class Command(BaseCommand):
    help = 'Send a single test SMS to a phone number. Creates a Message and AlertRecipient when --persist is set.'

    def add_arguments(self, parser):
        parser.add_argument('--number', '-n', required=True, help='Phone number to send to (include country code, e.g. +233... )')
        parser.add_argument('--message', '-m', default='Test SMS from school alert system', help='Message body')
        parser.add_argument('--school-slug', '-s', help='School slug to associate the Message with (optional)')
        parser.add_argument('--persist', action='store_true', help='Persist Message and AlertRecipient to DB')

    def handle(self, *args, **options):
        number = options['number']
        body = options['message']
        school = None
        if options.get('school_slug'):
            try:
                school = School.objects.get(slug=options['school_slug'])
            except School.DoesNotExist:
                raise CommandError(f"School with slug '{options['school_slug']}' not found")

        self.stdout.write(f"Sending test SMS to {number}...")
        try:
            message_id = send_sms(number, body, school)
            self.stdout.write(self.style.SUCCESS(f"Provider message id: {message_id}"))
        except Exception as e:
            raise CommandError(f"Send failed: {e}")

        if options.get('persist'):
            # create minimal Message and AlertRecipient records
            msg = Message.objects.create(school=school or (School.objects.first() if School.objects.exists() else None),
                                         content=body,
                                         scheduled_time=timezone.now(),
                                         sent=True)
            # create a Parent placeholder if none exists with this number
            parent = Parent.objects.filter(phone_number=number).first()
            if not parent:
                parent = Parent.objects.create(school=msg.school, name='Test Parent', phone_number=number)
            ar = AlertRecipient.objects.create(message=msg, parent=parent, status='pending')
            ar.provider_message_id = message_id
            ar.sent_at = timezone.now()
            ar.status = 'sent'
            ar.save()
            self.stdout.write(self.style.SUCCESS(f"Persisted Message(id={msg.id}) and AlertRecipient(id={ar.id})"))