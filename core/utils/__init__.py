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


def validate_sms_balance(organization, num_messages, settings):
	"""
	Validate if organization has sufficient balance for SMS sending (pay-as-you-go model).

	Args:
		organization: Organization instance
		num_messages: Number of SMS messages to send
		settings: Django settings object

	Returns:
		tuple: (is_valid: bool, error_message: str or None)
	"""
	# Calculate cost for messages (₵0.25 per SMS)
	cost_per_sms = organization.sms_rate if hasattr(organization, 'sms_rate') else 0.25
	total_cost = num_messages * cost_per_sms

	# Check if organization has sufficient balance
	if organization.balance < total_cost:
		return False, f"Insufficient balance. Required: ₵{total_cost:.2f}, Available: ₵{organization.balance:.2f}. Please top up your account."

	# Check if organization is active
	if not organization.is_active:
		return False, "Organization account is not active. Please contact support."

	return True, None


def deduct_sms_balance(organization, num_messages, settings):
	"""
	Deduct SMS cost from organization balance (pay-as-you-go model).

	Args:
		organization: Organization instance
		num_messages: Number of SMS messages sent
		settings: Django settings object

	Returns:
		float: Amount deducted from balance
	"""
	# Calculate cost for messages (₵0.25 per SMS)
	cost_per_sms = organization.sms_rate if hasattr(organization, 'sms_rate') else 0.25
	total_cost = num_messages * cost_per_sms

	# Deduct from balance
	organization.balance -= total_cost
	organization.save()

	# Update total SMS sent counter
	organization.total_sms_sent += num_messages
	organization.save()

	return total_cost


from . import crypto_utils

__all__ = ["normalize_phone_number"]
