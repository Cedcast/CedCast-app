import clicksend_client
from clicksend_client import SMSApi, SmsMessage, SmsMessageCollection
from clicksend_client.rest import ApiException
from core.models import School
from django.conf import settings
from core.utils.crypto_utils import decrypt_value
import logging

logger = logging.getLogger(__name__)


def send_sms(to_number, message_body, school: School):
    """
    Send SMS using ClickSend API
    
    Args:
        to_number (str): Recipient phone number (should include country code)
        message_body (str): Message content
        school (School): School instance with ClickSend credentials
    
    Returns:
        str: Message ID from ClickSend
    
    Raises:
        Exception: If ClickSend credentials not configured or API call fails
    """
    # NOTE: dry-run simulation removed so dev server will perform live sends.
    # To re-enable dry-run, restore checks here (CLICKSEND_DRY_RUN).

    # Get ClickSend credentials
    username_raw = getattr(settings, 'CLICKSEND_USERNAME', None) or school.clicksend_username
    api_key_raw = getattr(settings, 'CLICKSEND_API_KEY', None) or school.clicksend_api_key
    username = decrypt_value(username_raw) if username_raw else None
    api_key = decrypt_value(api_key_raw) if api_key_raw else None
    
    if not (username and api_key):
        raise Exception("ClickSend credentials not configured.")
    
    # Configure ClickSend client
    configuration = clicksend_client.Configuration()
    configuration.username = username
    configuration.password = api_key
    
    # Create API instance
    api_instance = SMSApi(clicksend_client.ApiClient(configuration))
    
    # Prepare SMS message
    # Optional sender ID support (ClickSend 'from')
    sender_id_raw = getattr(school, 'sender_id', None)
    sender_id = decrypt_value(sender_id_raw) if sender_id_raw else None
    sms_message = SmsMessage(
        source="django",
        body=message_body,
        to=to_number,
        _from=sender_id if sender_id else None,
        custom_string="school_alert"
    )
    
    sms_messages = SmsMessageCollection(messages=[sms_message])
    
    try:
    # Send SMS
        api_response = api_instance.sms_send_post(sms_messages)
        
        # Check if the message was sent successfully
        if api_response.response_code == "SUCCESS":
            # Return the message ID
            if api_response.data.messages and len(api_response.data.messages) > 0:
                return api_response.data.messages[0].message_id
            else:
                raise Exception("No message ID returned from ClickSend")
        else:
            raise Exception(f"ClickSend API error: {api_response.response_msg}")
            
    except ApiException as e:
        logger.exception("ClickSend API exception during sms_send_post")
        raise Exception(f"ClickSend API exception: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error during sms_send_post")
        raise Exception(f"Error sending SMS: {str(e)}")


def get_sms_delivery_status(message_id, school: School):
    """
    Check delivery status of a sent SMS
    
    Args:
        message_id (str): ClickSend message ID
        school (School): School instance with ClickSend credentials
    
    Returns:
        dict: Delivery status information
    """
    # For local dev we now query ClickSend for real status; remove dry-run mocks.

    # Get ClickSend credentials
    username = getattr(settings, 'CLICKSEND_USERNAME', None) or school.clicksend_username
    api_key = getattr(settings, 'CLICKSEND_API_KEY', None) or school.clicksend_api_key
    
    if not (username and api_key):
        raise Exception("ClickSend credentials not configured.")
    
    # Configure ClickSend client
    configuration = clicksend_client.Configuration()
    configuration.username = username
    configuration.password = api_key
    
    # Create API instance
    api_instance = SMSApi(clicksend_client.ApiClient(configuration))
    
    try:
        # Get message status
        api_response = api_instance.sms_history_export_get(
            filename="delivery_status",
            message_id=message_id
        )
        
        return {
            'status': api_response.response_code,
            'data': api_response.data
        }
        
    except ApiException as e:
        logger.exception("ClickSend API exception during status check")
        raise Exception(f"ClickSend API exception: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error during status check")
        raise Exception(f"Error checking delivery status: {str(e)}")