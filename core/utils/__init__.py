import re


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


from . import crypto_utils

__all__ = ["normalize_phone_number"]
