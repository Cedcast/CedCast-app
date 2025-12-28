"""
Application constants and configuration values.
Centralized location for all app-wide constants to avoid magic numbers and strings.
"""

from decimal import Decimal

# SMS Configuration
MAX_SMS_LENGTH = 160
SMS_PROVIDER_COST = Decimal('0.03')  # Cost per SMS from providers
SMS_CUSTOMER_RATE = Decimal('0.14')  # What we charge customers per SMS
SMS_MIN_BALANCE = Decimal('1.00')  # Minimum balance required

# Payment Configuration
MAX_PAYMENT_AMOUNT = Decimal('10000.00')  # Maximum payment amount in GHS
MIN_PAYMENT_AMOUNT = Decimal('10.00')  # Minimum payment amount in GHS

# Application Limits
DEFAULT_DASHBOARD_MESSAGES_LIMIT = 10
TREND_DAYS = 7
ORG_MESSAGE_MAX_RETRIES = 3

# Paystack Configuration
PAYSTACK_BASE_URL = 'https://api.paystack.co'

# File Upload Limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_FILE_TYPES = ['text/csv', 'application/pdf', 'text/plain']

# Cache Timeouts (in seconds)
CACHE_TIMEOUT_DASHBOARD = 300  # 5 minutes
CACHE_TIMEOUT_CONTACTS = 600   # 10 minutes

# UI Constants
DEFAULT_PAGE_SIZE = 25
MAX_CONTACTS_PER_UPLOAD = 1000