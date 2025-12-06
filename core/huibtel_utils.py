"""
Backward-compatible shim for the misspelled `huibtel_utils` name.
This module forwards to `core.hubtel_utils` (the canonical implementation).
"""

from core.hubtel_utils import send_sms, get_sms_delivery_status  # re-export

__all__ = ["send_sms", "get_sms_delivery_status"]
