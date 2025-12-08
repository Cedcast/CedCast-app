import logging
import os
from django.conf import settings
from core.models import School
from core.utils.crypto_utils import decrypt_value

logger = logging.getLogger(__name__)


def send_sms(to_number, message_body, tenant: School):
    """
    Send SMS using a local Hubtel-compatible endpoint.

    Arguments:
        to_number (str): recipient phone number
        message_body (str): message text
        tenant (School or Organization): tenant instance that may contain sender_id

    Returns:
        str: message id (real or fake in dry-run)
    """
    # NOTE: removed dry-run simulation so dev server will perform live sends.
    # If you want to temporarily simulate sends, set HUBTEL_DRY_RUN handling back here.

    # Always perform a live send via Hubtel

    # Prefer tenant-specific Hubtel configuration if provided (set during onboarding)
    api_url = getattr(tenant, 'hubtel_api_url', None) or getattr(settings, 'HUBTEL_API_URL', None)
    client_id_raw = getattr(tenant, 'hubtel_client_id', None) or getattr(settings, 'HUBTEL_CLIENT_ID', None)
    client_secret_raw = getattr(tenant, 'hubtel_client_secret', None) or getattr(settings, 'HUBTEL_CLIENT_SECRET', None) or getattr(settings, 'HUBTEL_API_KEY', None)
    client_id = decrypt_value(client_id_raw) if client_id_raw else None
    client_secret = decrypt_value(client_secret_raw) if client_secret_raw else None

    if not api_url:
        raise Exception("Hubtel API URL not configured (HUBTEL_API_URL or tenant.hubtel_api_url)")

    # Prefer a Hubtel-specific sender id if provided, otherwise fall back to generic sender_id
    sender_id_raw = getattr(tenant, 'hubtel_sender_id', None) or getattr(tenant, 'sender_id', None)
    # decrypt if encrypted (use module-level decrypt_value; avoid re-importing which makes it a local var)
    try:
        sender_id = decrypt_value(sender_id_raw) if sender_id_raw else None
    except Exception:
        sender_id = sender_id_raw

    # Use requests if available
    try:
        import requests
    except Exception as e:
        logger.exception("requests library is required for Hubtel integration")
        raise Exception("requests library is required to call Hubtel API")

    # Normalize numeric MSISDNs for testing with numeric senders
    def _normalize_number(n: str) -> str | None:
        if not n:
            return None
        # strip leading + and whitespace; keep international digits
        return n.lstrip('+').strip()

    to_norm = _normalize_number(to_number)
    from_norm = _normalize_number(sender_id) if sender_id else None
    # If tenant doesn't provide a sender, fall back to a configured default
    if not from_norm:
        default_sender = getattr(settings, 'HUBTEL_DEFAULT_SENDER', None)
        if default_sender:
            from_norm = _normalize_number(default_sender)

    # Hubtel expects client credentials and content as query params. Use an
    # explicit ordered list of tuples so the query param order matches the
    # examples you provided during testing (clientid, clientsecret, from, to, content).
    params = [
        ('clientid', client_id),
        ('clientsecret', client_secret),
    ]
    if from_norm:
        params.append(('from', from_norm))
    params.append(('to', to_norm if to_norm is not None else to_number))
    params.append(('content', message_body))

    try:
        resp = requests.get(api_url, params=params, timeout=15)
        resp.raise_for_status()
        # Hubtel may return JSON or plain text. Try JSON first.
        try:
            data = resp.json()
        except Exception:
            data = {'response_text': resp.text}

        # Heuristic: common Hubtel responses include message id under various keys
        message_id = None
        if isinstance(data, dict):
            for key in ('message_id', 'messageId', 'id', 'MessageId'):
                if key in data:
                    message_id = data.get(key)
                    break
            # fallback to any 'response_text' or stringified dict
            if not message_id:
                message_id = data.get('response_text') or str(data)
        else:
            message_id = str(data)

        return message_id
    except Exception as e:
        logger.exception("Error sending SMS via Hubtel: %s", e)
        raise Exception(f"Hubtel send error: {e}")


def get_sms_delivery_status(message_id, tenant: School):
    """
    Query Hubtel for delivery status.
    """

    api_url = getattr(settings, 'HUBTEL_API_URL', None)
    api_key = getattr(settings, 'HUBTEL_API_KEY', None)

    if not api_url:
        raise Exception("Hubtel API URL not configured (HUBTEL_API_URL)")

    try:
        import requests
    except Exception:
        raise Exception("requests library is required to query Hubtel delivery status")

    headers = {}
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"

    try:
        resp = requests.get(f"{api_url.rstrip('/')}/status/{message_id}", headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.exception("Error checking Hubtel message status: %s", e)
        raise Exception(f"Hubtel status error: {e}")
