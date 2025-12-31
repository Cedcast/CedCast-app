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
    Falls back to legacy organization-based sending if no sender assigned.

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
    
    if sender:
        # Use new sender pool system
        return _send_via_sender_pool(organization, message, sms_body, user, sender)
    else:
        # Fall back to legacy organization-based sending
        logger.warning(f"No sender assigned to organization {organization.slug}, falling back to legacy SMS sending")
        return _send_via_legacy_system(organization, message, sms_body, user)


def _send_via_sender_pool(organization, message, sms_body, user, sender):
    """Send SMS using the assigned sender from the pool."""
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
            processed += 1
        else:
            ar.status = 'failed'
        ar.save()

    # Deduct balances
    if processed > 0:
        sender.deduct_gateway_balance(processed)
        organization.deduct_sms_cost(processed)

    # Update message status
    message.sent = True
    message.save()

    return processed, organization.get_current_sms_rate() * processed, sender


def _send_via_legacy_system(organization, message, sms_body, user):
    """Fallback SMS sending using legacy organization-based credentials."""
    from .. import hubtel_utils
    
    processed = 0
    total_cost = Decimal('0')
    sent_ids = []

    # Check organization credit balance first
    recipient_count = message.recipients_status.count()
    required_credits = organization.get_current_sms_rate() * recipient_count
    if organization.sms_credit_balance < required_credits:
        raise Exception("Insufficient SMS credits. Please top up your balance.")

    # Send using organization's legacy credentials
    for ar in message.recipients_status.all():
        try:
            # Use legacy hubtel_utils.send_sms function
            sent_id = hubtel_utils.send_sms(
                to_number=ar.contact.phone_number,
                message_body=sms_body,
                tenant=organization  # Pass organization as tenant
            )
            sent_ids.append(sent_id)
            ar.provider_message_id = str(sent_id)
            ar.status = 'sent'
            ar.sent_at = timezone.now()
            processed += 1
        except Exception as e:
            logger.error(f"Failed to send SMS to {ar.contact.phone_number}: {str(e)}")
            ar.status = 'failed'
            ar.error_message = str(e)
            sent_ids.append(None)
        ar.save()

    # Deduct balance for successful sends
    if processed > 0:
        organization.deduct_sms_cost(processed)
        total_cost = organization.get_current_sms_rate() * processed

    # Update message status
    message.sent = True
    message.save()

    # Audit log
    AuditLog.objects.create(
        user=user,
        organization=organization,
        action='sms_sent_legacy',
        details={
            'recipients_count': processed,
            'total_cost': str(total_cost),
            'message_id': message.id,
            'fallback_used': True
        },
    )

    return processed, total_cost, None
