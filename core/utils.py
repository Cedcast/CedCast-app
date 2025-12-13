import re
from decimal import Decimal


def normalize_phone_number(raw: str, default_country='+233') -> str | None:
    """Normalize phone numbers into E.164-like format for this project.

    Rules (configurable here):
    - Strip non-digit and non-plus characters
    - If starts with '+', keep as-is (after stripping non-digits)
    - If starts with '0', replace leading 0 with default_country (e.g., +233)
    - If digits only and length looks local (8-10 digits), prepend default_country
    - Returns None for empty/invalid inputs

    Note: This is a pragmatic normalizer for Ghana numbers by default.
    If you want a different policy, update default_country or extend logic.
    """
    if not raw:
        return None
    s = str(raw).strip()
    # Remove common separators and letters
    # Keep leading + if present, else only digits
    if s.startswith('+'):
        cleaned = '+' + re.sub(r'[^0-9]', '', s[1:])
    else:
        cleaned = re.sub(r'[^0-9]', '', s)

    if not cleaned:
        return None

    # If starts with + and has digits, return
    if cleaned.startswith('+'):
        return cleaned

    # If starts with 0, replace leading 0 with country code without plus
    if cleaned.startswith('0'):
        # remove leading 0s
        without0 = cleaned.lstrip('0')
        return default_country + without0

    # If digits length looks like local national (7-10 digits), prepend default
    if 7 <= len(cleaned) <= 10:
        return default_country + cleaned

    # Otherwise, if it's longer (international without +), try prefixing +
    if len(cleaned) > 10:
        return '+' + cleaned

    return None


def validate_sms_balance(organization, recipient_count: int, settings) -> tuple[bool, str]:
    """
    Validate if organization has sufficient balance for SMS sending.

    Args:
        organization: Organization instance
        recipient_count: Number of recipients
        settings: Django settings module

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    customer_rate = getattr(settings, 'SMS_CUSTOMER_RATE', Decimal('0.10'))
    min_balance = getattr(settings, 'SMS_MIN_BALANCE', Decimal('1.00'))
    estimated_cost = recipient_count * customer_rate

    if organization.balance < min_balance:
        return False, f'Insufficient balance. Minimum balance required: ₵{min_balance}. Your balance: ₵{organization.balance}.'

    if organization.balance < estimated_cost:
        return False, f'Insufficient balance for {recipient_count} recipients. Estimated cost: ₵{estimated_cost}. Your balance: ₵{organization.balance}.'

    return True, ""


def deduct_sms_balance(organization, recipient_count: int, settings) -> Decimal:
    """
    Deduct SMS cost from organization balance.

    Args:
        organization: Organization instance
        recipient_count: Number of recipients successfully sent
        settings: Django settings module

    Returns:
        Decimal: Actual cost deducted
    """
    customer_rate = getattr(settings, 'SMS_CUSTOMER_RATE', Decimal('0.10'))
    actual_cost = recipient_count * customer_rate
    organization.balance -= actual_cost
    organization.save()
    return actual_cost
