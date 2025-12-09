from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Message, AlertRecipient
from core.hubtel_utils import send_sms

class Command(BaseCommand):
    help = 'Send scheduled SMS messages that are due.'

    def handle(self, *args, **options):
        now = timezone.now()
        messages = Message.objects.filter(sent=False)
        for message in messages:
            # Ensure scheduled_time is timezone-aware; if naive, assume settings timezone and persist the change
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
                # best-effort: skip bad timestamp
                continue
            # Only process messages that are due
            if sched > now:
                continue
            recipients = message.recipients.all()
            for parent in recipients:
                alert_recipient = AlertRecipient.objects.get(message=message, parent=parent)
                if alert_recipient.status == 'pending':
                    try:
                        message_id = send_sms(parent.phone_number, message.content, message.school)
                        # persist provider message id for later delivery receipts
                        alert_recipient.provider_message_id = message_id
                        alert_recipient.status = 'sent'
                        alert_recipient.sent_at = now
                        alert_recipient.error_message = ''
                    except Exception as e:
                        alert_recipient.status = 'failed'
                        alert_recipient.error_message = str(e)
                    alert_recipient.save()
            message.sent = True
            message.save()
        self.stdout.write(self.style.SUCCESS('Scheduled messages processed.'))
