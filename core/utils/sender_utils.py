import logging
from decimal import Decimal
from django.utils import timezone
from ..models import Sender, SenderAssignment, AuditLog

logger = logging.getLogger(__name__)


def get_sender_for_organization(organization):
    """
    Get an active sender assigned to the organization.
    Returns the first available sender or None.
    """
    try:
        assignment = SenderAssignment.objects.filter(
            organization=organization,
            is_active=True,
            sender__status__in=['available', 'assigned']
        ).select_related('sender').first()

        if assignment:
            return assignment.sender
    except Exception as e:
        logger.error(f"Error getting sender for organization {organization.slug}: {str(e)}")

    return None


def send_sms_through_sender_pool(organization, message, sms_body, user):
    """
    Send SMS through the assigned sender in the sender pool.

    Args:
        organization: Organization instance
        message: OrgMessage instance
        sms_body: SMS content
        user: User who initiated the send

    Returns:
        tuple: (processed_count, total_cost, sender_used)
    """
    # Get assigned sender
    sender = get_sender_for_organization(organization)
    if not sender:
        raise Exception("No active sender assigned to this organization. Please contact support.")

    # Check sender gateway balance
    if not sender.can_send_sms(message.recipients_status.count()):
        # Log low balance
        AuditLog.objects.create(
            user=user,  # Can be None for background commands
            organization=organization,
            sender=sender,
            action='gateway_balance_low',
            details={'required': message.recipients_status.count(), 'available': str(sender.gateway_balance)},
        )
        raise Exception("Sender gateway balance is insufficient. Please contact support.")

    # Check organization credit balance
    recipient_count = message.recipients_status.count()
    required_credits = organization.get_current_sms_rate() * recipient_count
    if organization.sms_credit_balance < required_credits:
        raise Exception("Insufficient SMS credits. Please top up your balance.")

    processed = 0
    total_cost = Decimal('0')

    # Send through the appropriate provider
    if sender.provider == 'hubtel':
        sent_ids = send_via_hubtel(sender, message, sms_body)
    elif sender.provider == 'clicksend':
        sent_ids = send_via_clicksend(sender, message, sms_body)
    else:
        raise Exception(f"Unsupported provider: {sender.provider}")

    # Update recipients and deduct balances
    for ar, sent_id in zip(message.recipients_status.all(), sent_ids):
        if sent_id:
            ar.provider_message_id = str(sent_id)
            ar.status = 'sent'
            ar.sent_at = timezone.now()
            ar.error_message = ''
            ar.save()
            processed += 1
        else:
            ar.status = 'failed'
            ar.error_message = 'Provider error'
            ar.save()

    if processed > 0:
        # Deduct from organization credits
        cost = organization.get_current_sms_rate() * processed
        organization.sms_credit_balance -= cost
        organization.total_sms_sent += processed
        organization.save(update_fields=['sms_credit_balance', 'total_sms_sent'])
        total_cost = cost

        # Deduct from sender gateway balance
        sender.deduct_gateway_balance(processed)

        # Audit log
        AuditLog.objects.create(
            user=user,  # Can be None for background commands
            organization=organization,
            sender=sender,
            action='sms_sent',
            details={
                'message_id': message.id,
                'recipients': processed,
                'cost': str(total_cost),
                'sender_used': sender.name
            },
        )

    return processed, total_cost, sender


def send_via_hubtel(sender, message, sms_body):
    """Send SMS via Hubtel using sender credentials"""
    from .. import hubtel_utils

    sent_ids = []
    for ar in message.recipients_status.all():
        try:
            # Use sender's credentials instead of organization's
            sent_id = hubtel_utils.send_sms_with_credentials(
                phone=ar.contact.phone_number,
                message=sms_body,
                api_url=sender.hubtel_api_url,
                client_id=sender.hubtel_client_id,
                client_secret=sender.hubtel_client_secret,
                api_key=sender.hubtel_api_key,
                sender_id=sender.sender_id
            )
            sent_ids.append(sent_id)
        except Exception as e:
            logger.error(f"Hubtel send failed for {ar.contact.phone_number}: {str(e)}")
            sent_ids.append(None)
    return sent_ids


def send_via_clicksend(sender, message, sms_body):
    """Send SMS via ClickSend using sender credentials"""
    try:
        from .. import clicksend_utils
    except ImportError:
        raise Exception("ClickSend integration not available")

    sent_ids = []
    for ar in message.recipients_status.all():
        try:
            sent_id = clicksend_utils.send_sms_with_credentials(
                phone=ar.contact.phone_number,
                message=sms_body,
                username=sender.clicksend_username,
                api_key=sender.clicksend_api_key,
                sender_id=sender.sender_id
            )
            sent_ids.append(sent_id)
        except Exception as e:
            logger.error(f"ClickSend send failed for {ar.contact.phone_number}: {str(e)}")
            sent_ids.append(None)
    return sent_ids