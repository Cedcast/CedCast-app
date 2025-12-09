from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import OrgMessage, OrgAlertRecipient
from core.hubtel_utils import send_sms


class Command(BaseCommand):
    help = 'Send scheduled SMS messages for organizations that are due.'

    def handle(self, *args, **options):
        now = timezone.now()
        messages = OrgMessage.objects.filter(sent=False)
        for message in messages:
            sched = message.scheduled_time
            try:
                if sched is None:
                    continue
                if sched.tzinfo is None:
                    aware = timezone.make_aware(sched)
                    message.scheduled_time = aware
                    message.save(update_fields=['scheduled_time'])
                    sched = aware
            except Exception:
                continue
            if sched > now:
                continue

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
