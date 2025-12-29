from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
import logging

from core.models import OrgAlertRecipient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send pending organization messages (process OrgAlertRecipient entries with status pending)'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Maximum recipients to process this run')
        parser.add_argument('--org', type=str, help='Process only recipients for org with this slug')
        parser.add_argument('--max-retries', type=int, default=getattr(settings, 'ORG_MESSAGE_MAX_RETRIES', 3), help='Max retry attempts before final failure')
        parser.add_argument('--dry-run', action='store_true', help='Do not perform external sends (log only)')

    def handle(self, *args, **options):
        limit = options['limit']
        org_slug = options.get('org')
        max_retries = options.get('max_retries')
        dry_run = options.get('dry_run')

        now = timezone.now()

        # Avoid potential aware/naive datetime comparisons in DB filters by selecting
        # pending recipients and checking their message.scheduled_time in Python after normalizing.
        qs = OrgAlertRecipient.objects.filter(status='pending')
        if org_slug:
            qs = qs.filter(message__organization__slug=org_slug)

        qs = qs.order_by('id')[:limit]
        total = qs.count()
        self.stdout.write(f"Processing {total} pending recipients (dry_run={dry_run})")

        # Try to use ClickSend first, fallback to Hubtel if configured
        from core import hubtel_utils
        try:
            from core import clicksend_utils
        except Exception:
            clicksend_utils = None

        processed = 0
        for ar in qs:
            processed += 1
            phone = ar.contact.phone_number
            content = ar.message.content
            tenant = getattr(ar.message, 'organization', None)
            
            # Skip if organization is not active (banned)
            if tenant and not tenant.is_active:
                self.stdout.write(f"Skipping {phone}: organization '{tenant.name}' is banned")
                ar.status = 'failed'
                ar.error_message = 'Organization is banned'
                ar.save()
                continue
            # normalize message scheduled_time if naive and skip if not yet due
            try:
                sched = ar.message.scheduled_time
                if sched is None:
                    continue
                if sched.tzinfo is None:
                    sched = timezone.make_aware(sched)
                    ar.message.scheduled_time = sched
                    ar.message.save(update_fields=['scheduled_time'])
                if sched > now:
                    # message not yet due; skip
                    continue
            except Exception:
                # if we can't parse scheduled_time, skip this recipient for now
                continue
            try:
                if dry_run:
                    self.stdout.write(f"[DRY] Would send to {phone}: {content[:60]}")
                    # mark as sent in dry-run for convenience
                    ar.provider_message_id = f"dryrun-{ar.id}"
                    ar.status = 'sent'
                    ar.sent_at = timezone.now()
                    ar.save()
                    continue

                # Prefer Hubtel as the primary provider; fall back to ClickSend when Hubtel fails or is not configured
                sent_id = None
                try:
                    sent_id = hubtel_utils.send_sms(phone, content, tenant)
                except Exception as e_hub:
                    logger.warning("Hubtel send failed for %s: %s", phone, e_hub)
                    if clicksend_utils is not None:
                        try:
                            sent_id = clicksend_utils.send_sms(phone, content, tenant)
                        except Exception as e_click:
                            raise Exception(f"Hubtel error: {e_hub}; ClickSend error: {e_click}")
                    else:
                        raise Exception(f"Hubtel error: {e_hub}; ClickSend not available")

                # success
                ar.provider_message_id = str(sent_id)
                ar.status = 'sent'
                ar.sent_at = timezone.now()
                ar.error_message = ''
                ar.save()

                # if all recipients for the message are sent, mark message.sent
                msg = ar.message
                pending_exists = msg.recipients_status.filter(status='pending').exists()
                if not pending_exists:
                    msg.sent = True
                    msg.save()

                self.stdout.write(f"Sent to {phone} (id={ar.provider_message_id})")

            except Exception as e:
                logger.exception("Failed sending to %s: %s", phone, e)
                # increment retry counter
                ar.retry_count = (ar.retry_count or 0) + 1
                ar.last_retry_at = timezone.now()
                ar.error_message = str(e)
                if ar.retry_count >= max_retries:
                    ar.status = 'failed'
                else:
                    ar.status = 'pending'
                ar.save()
                self.stdout.write(f"Failed {phone}: {e} (retry {ar.retry_count}/{max_retries})")

        self.stdout.write(f"Done — processed {processed} recipients")
