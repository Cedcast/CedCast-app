from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Retry failed organization alert recipients (background retry job)'

    def add_arguments(self, parser):
        parser.add_argument('--max-retries', type=int, default=3, help='Maximum retry attempts per recipient')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of recipients to process (0 = all)')

    def handle(self, *args, **options):
        max_retries = options.get('max_retries')
        limit = options.get('limit')

        from core.models import OrgAlertRecipient
        from core.hubtel_utils import send_sms

        qs = OrgAlertRecipient.objects.filter(status='failed').order_by('last_retry_at', 'id')
        if max_retries is not None:
            qs = qs.filter(retry_count__lt=max_retries)
        if limit and limit > 0:
            qs = qs[:limit]

        total = qs.count()
        processed = 0
        for ar in qs:
            try:
                msg = ar.message
                contact = ar.contact
                # Attempt resend
                message_id = send_sms(contact.phone_number, msg.content, contact.organization)
                ar.status = 'sent'
                ar.sent_at = timezone.now()
                ar.provider_message_id = message_id
                ar.error_message = ''
                ar.retry_count = (ar.retry_count or 0) + 1
                ar.last_retry_at = timezone.now()
                ar.save()
                processed += 1
            except Exception as e:
                ar.retry_count = (ar.retry_count or 0) + 1
                ar.last_retry_at = timezone.now()
                ar.error_message = str(e)
                ar.save()
                processed += 1

        self.stdout.write(self.style.SUCCESS(f'Retried {processed}/{total} failed recipients'))
