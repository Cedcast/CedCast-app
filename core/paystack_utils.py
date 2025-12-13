import logging
import requests
import re
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger(__name__)


def initialize_payment(email, amount, reference, callback_url=None):
    """
    Initialize a Paystack payment transaction.

    Arguments:
        email (str): customer's email
        amount (Decimal): amount in GHS (will be converted to pesewas)
        reference (str): unique transaction reference
        callback_url (str): URL to redirect after payment

    Returns:
        dict: Paystack response containing authorization_url and reference
    """
    if not settings.PAYSTACK_SECRET_KEY:
        raise Exception("Paystack secret key not configured")

    # Validate email format (more permissive)
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        logger.error(f"Invalid or missing email: {email}")
        raise Exception(f"Invalid or missing email address. Please update your profile with a valid email.")

    # Validate amount
    if amount <= 0 or amount > 10000:
        raise Exception("Amount must be between 0.01 and 10,000 GHS")

    url = f"{settings.PAYSTACK_BASE_URL}/transaction/initialize"
    headers = {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json'
    }

    # Convert amount to pesewas (Paystack expects amount in smallest currency unit)
    amount_pesewas = int(amount * 100)

    data = {
        'email': email,
        'amount': amount_pesewas,
        'reference': reference,
        'currency': 'GHS'
    }

    if callback_url:
        data['callback_url'] = callback_url

    try:
        logger.info(f"Paystack init request: email={email}, amount={amount_pesewas}, reference={reference}, callback_url={callback_url}")
        response = requests.post(url, json=data, headers=headers)
        logger.info(f"Paystack response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Paystack error response: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Paystack initialization failed: {e}")
        raise Exception(f"Payment initialization failed: {str(e)}")


def verify_payment(reference):
    """
    Verify a Paystack payment transaction.

    Arguments:
        reference (str): transaction reference

    Returns:
        dict: Paystack verification response
    """
    if not settings.PAYSTACK_SECRET_KEY:
        raise Exception("Paystack secret key not configured")

    url = f"{settings.PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    headers = {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Paystack verification failed: {e}")
        raise Exception(f"Payment verification failed: {str(e)}")


def get_payment_status(reference):
    """
    Get the status of a Paystack payment.

    Arguments:
        reference (str): transaction reference

    Returns:
        str: payment status ('success', 'failed', 'pending', etc.)
    """
    try:
        result = verify_payment(reference)
        return result['data']['status']
    except Exception as e:
        logger.error(f"Failed to get payment status: {e}")
        return 'failed'