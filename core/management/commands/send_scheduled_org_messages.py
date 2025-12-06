from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import OrgMessage, OrgAlertRecipient
from core.hubtel_utils import send_sms


class Command(BaseCommand):
    help = 'Send scheduled SMS messages for organizations that are due.'

    def handle(self, *args, **options):
        now = timezone.now()
        messages = OrgMessage.objects.filter(sent=False, scheduled_time__lte=now)
        for message in messages:
            recipients = message.recipients_status.all()
            for ar in recipients:
                if ar.status == 'pending':
                    try:
                        send_sms(ar.contact.phone_number, message.content, message.organization)
                        ar.status = 'sent'
                        ar.sent_at = now
                        ar.error_message = ''
                    except Exception as e:
                        ar.status = 'failed'
                        ar.error_message = str(e)
                    ar.save()
            message.sent = True
            message.save()
        self.stdout.write(self.style.SUCCESS('Scheduled organization messages processed.'))
