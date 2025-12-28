"""
Error handling utilities for consistent error responses and logging.
"""

import logging
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

class AppError(Exception):
    """Base exception class for application errors."""
    def __init__(self, message, status_code=400, user_message=None):
        self.message = message
        self.status_code = status_code
        self.user_message = user_message or message
        super().__init__(self.message)

class ValidationError(AppError):
    """Validation-related errors."""
    pass

class PaymentError(AppError):
    """Payment processing errors."""
    pass

class SMSProviderError(AppError):
    """SMS provider communication errors."""
    pass

def handle_view_error(request, exception, template_name=None, context=None):
    """
    Standardized error handling for view functions.
    Logs the error and returns appropriate response.
    """
    logger.error(f"View error in {request.path}: {str(exception)}", exc_info=True)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # AJAX request - return JSON error
        return JsonResponse({
            'success': False,
            'message': getattr(exception, 'user_message', 'An unexpected error occurred. Please try again.')
        }, status=getattr(exception, 'status_code', 500))

    # Regular request - render template with error
    if template_name:
        context = context or {}
        context['error'] = getattr(exception, 'user_message', 'An unexpected error occurred.')
        return render(request, template_name, context)

    # Fallback - redirect to home with error message
    from django.contrib import messages
    messages.error(request, getattr(exception, 'user_message', 'An unexpected error occurred.'))
    from django.shortcuts import redirect
    return redirect('home')

def log_and_continue(func):
    """
    Decorator to log exceptions but continue execution.
    Useful for non-critical operations.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Non-critical error in {func.__name__}: {str(e)}")
            return None
    return wrapper

# Common error messages
ERROR_MESSAGES = {
    'file_too_large': 'File size exceeds the maximum allowed limit.',
    'invalid_file_type': 'File type not supported. Please upload a CSV, PDF, or text file.',
    'payment_failed': 'Payment processing failed. Please try again or contact support.',
    'insufficient_balance': 'Insufficient balance. Please top up your account.',
    'sms_send_failed': 'Failed to send SMS. Please try again later.',
    'contact_not_found': 'Contact not found.',
    'unauthorized': 'You do not have permission to perform this action.',
    'rate_limit_exceeded': 'Too many requests. Please wait and try again.',
}