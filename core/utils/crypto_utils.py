from django.conf import settings
from django.core import signing
import base64
import logging

logger = logging.getLogger(__name__)

_FERNET = None
_FERNET_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
    # Prefer explicit key
    key = getattr(settings, 'SMS_ENCRYPTION_KEY', None)
    if key:
        if isinstance(key, str):
            key = key.encode()
    else:
        # Derive a 32-byte key from SECRET_KEY (best-effort). Fernet expects 32 urlsafe base64 bytes.
        raw = settings.SECRET_KEY.encode('utf-8')
        key = base64.urlsafe_b64encode(raw[:32].ljust(32, b'0'))
    _FERNET = Fernet(key)
except Exception:
    _FERNET_AVAILABLE = False


def encrypt_value(value: str) -> str:
    """Encrypt/sign a string and return a stored representation prefixed with ENC::."""
    if value is None or value == "":
        return value
    try:
        if _FERNET_AVAILABLE and _FERNET is not None:
            token = _FERNET.encrypt(value.encode('utf-8')).decode('utf-8')
            return f"ENC::{token}"
        else:
            # Fallback: use django signing (not encryption but signed)
            token = signing.dumps(value)
            return f"ENC::{token}"
    except Exception as e:
        logger.exception("Failed to encrypt value: %s", e)
        # As a last resort, store plaintext (shouldn't happen)
        return value


def decrypt_value(stored: str) -> str:
    """Decrypt or verify a stored representation. If not prefixed with ENC::, return as-is."""
    if stored is None or stored == "":
        return stored
    if not isinstance(stored, str):
        return stored
    if not stored.startswith('ENC::'):
        return stored
    payload = stored[len('ENC::'):]
    try:
        if _FERNET_AVAILABLE and _FERNET is not None:
            return _FERNET.decrypt(payload.encode('utf-8')).decode('utf-8')
        else:
            return signing.loads(payload)
    except Exception as e:
        logger.exception("Failed to decrypt value: %s", e)
        # Return payload to avoid breaking callers; it's not decryptable
        return payload


def is_encrypted(stored: str) -> bool:
    return isinstance(stored, str) and stored.startswith('ENC::')
