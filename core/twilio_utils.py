from twilio.rest import Client
from core.models import School

def send_sms(to_number, message_body, school: School):
    from django.conf import settings
    # Use global Twilio credentials from settings.py
    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    if not (account_sid and auth_token and school.twilio_phone_number):
        raise Exception("Twilio credentials or school sender ID not configured.")
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=message_body,
        from_=school.twilio_phone_number,
        to=to_number
    )
    return message.sid
