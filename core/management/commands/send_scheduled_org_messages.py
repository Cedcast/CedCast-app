from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import OrgMessage, OrgAlertRecipient
from core.hubtel_utils import send_sms
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Send scheduled SMS messages for organizations that are due.'

    def handle(self, *args, **options):
        now = timezone.now()
        messages = OrgMessage.objects.filter(sent=False)
        for message in messages:
            # Skip if organization is not active (banned)
            if not message.organization.is_active:
                self.stdout.write(f"Skipping message {message.id}: organization '{message.organization.name}' is banned")
                # Mark all pending recipients as failed
                for ar in message.recipients_status.filter(status='pending'):
                    ar.status = 'failed'
                    ar.error_message = 'Organization is banned'
                    ar.save()
                message.sent = True  # Mark as processed to avoid reprocessing
                message.save()
                continue
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
            # Notify creator via email if available
            try:
                creator = getattr(message, 'created_by', None)
                if creator and getattr(creator, 'email', None):
                    subj = f"Scheduled message sent - {message.organization.name}"
                    body = f"Your scheduled message (ID: {message.id}) was sent on {now.strftime('%B %d, %Y at %I:%M %p')}.\n\nContent:\n{message.content}\n\nOrganization: {message.organization.name}"
                    send_mail(subj, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None) or '', [creator.email], fail_silently=True)
                    # Also add an in-app notification entry in cache for the creator
                    try:
                        if creator and getattr(creator, 'id', None):
                            key = f"sent_notifications_user_{creator.id}"
                            existing = cache.get(key, []) or []
                            existing.append({
                                'message_id': message.id,
                                'content': message.content,
                                'sent_at': now.strftime('%B %d, %Y at %I:%M %p'),
                                'organization': message.organization.name,
                            })
                            cache.set(key, existing, timeout=60 * 60 * 24)  # keep for 24 hours
                    except Exception:
                        pass
            except Exception:
                pass
        self.stdout.write(self.style.SUCCESS('Scheduled organization messages processed.'))
