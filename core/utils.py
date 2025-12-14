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
    Validate if organization has sufficient SMS for sending based on package.

    Args:
        organization: Organization instance
        recipient_count: Number of recipients
        settings: Django settings module

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    from django.utils import timezone

    # Check if organization has an active package
    if not organization.current_package:
        return False, "No active package. Please purchase a package to send SMS."

    # Check package expiry for expiry packages
    if organization.current_package.package_type == 'expiry':
        if not organization.package_expiry_date or organization.package_expiry_date < timezone.now():
            return False, "Your package has expired. Please renew your package."

    # Check SMS remaining
    if organization.sms_remaining < recipient_count:
        return False, f"Insufficient SMS in package. Required: {recipient_count}, Available: {organization.sms_remaining}. Please purchase more SMS."

    return True, ""


def deduct_sms_balance(organization, recipient_count: int, settings) -> int:
    """
    Deduct SMS count from organization package.

    Args:
        organization: Organization instance
        recipient_count: Number of recipients successfully sent
        settings: Django settings module

    Returns:
        int: Number of SMS deducted
    """
    organization.sms_remaining -= recipient_count
    organization.save()
    return recipient_count
