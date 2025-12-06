# Migration from Twilio to Hubtel (local SMS holder) - Setup Guide

## Overview
This guide will help you migrate your Django school alert system from Twilio/ClickSend to a local Hubtel-compatible SMS holder. Hubtel is a lightweight local service (or hosted gateway) that accepts HTTP requests and returns a message id; it's handy for rapid testing and for managing alpha-numeric sender IDs in small deployments.

## Prerequisites
1. A local Hubtel-compatible service (or other local SMS holder) running and reachable from the app (example: http://localhost:9000)
2. Python virtual environment
3. Django project setup

## Step 1: Configure your local Hubtel service

If you don't have an existing local SMS service, you can run a simple mock that accepts the Hubtel send endpoint and a status endpoint. Hubtel's send endpoint format is:

```
https://smsc.hubtel.com/v1/messages/send?clientid=string&clientsecret=string&from=string&to=string&content=string
```

The app will call the configured `HUBTEL_API_URL` with the above query parameters. The project expects a JSON response like `{"message_id": "abc123"}` or a plain response containing an id.

## Step 2: Update Environment Variables

Update your `.env` file with Hubtel configuration (for live sending set HUBTEL_DRY_RUN=false):

```
# Hubtel API URL
HUBTEL_API_URL=http://localhost:9000
# Optional API key used by your service
HUBTEL_API_KEY=
HUBTEL_DRY_RUN=false
```

## Step 3: Run Database Migration

```bash
# Create and apply the migration
python manage.py makemigrations core
python manage.py migrate
```

## Step 4: Update Existing Schools (Optional)

If you have existing schools with Twilio or ClickSend credentials, you can migrate them to Hubtel by setting a `sender_id` or the HUBTEL_* settings.

```python
# Run this in Django shell: python manage.py shell
from core.models import School

# Example: set a shared sender_id for all schools
for school in School.objects.all():
   school.sender_id = "SCHOOLID"
   school.save()
```

## Step 5: Test SMS Functionality

1. Start your Django development server:
   ```bash
   python manage.py runserver
   ```

2. Log in as a school admin
3. Try sending a test SMS
4. Check your Hubtel service logs or status endpoint for delivery status

## Step 6: Remove Twilio Dependencies (Optional)

After confirming everything works:

1. Uninstall Twilio:
   ```bash
   pip uninstall twilio
   ```

2. Remove Twilio fields from models (create new migration):
   ```python
   # In a new migration file
   operations = [
       migrations.RemoveField(
           model_name='school',
           name='twilio_account_sid',
       ),
       migrations.RemoveField(
           model_name='school',
           name='twilio_auth_token',
       ),
       migrations.RemoveField(
           model_name='school',
           name='twilio_phone_number',
       ),
   ]
   ```

## Key Changes Made

### Files Modified:
- `core/hubtel_utils.py` - New Hubtel SMS utility
- `core/models.py` - Uses `sender_id` for tenant-level alphanumeric sender support
- `core/views.py` - Updated to use Hubtel utility
- `core/management/commands/send_scheduled_messages.py` - Updated import
- `school_alert_system/settings.py` - Updated environment variables
- `core/templates/super_admin_dashboard.html` - Updated form fields
- `.env` - Updated with Hubtel configuration

### New Files:
 - `core/hubtel_utils.py` - Hubtel integration utility
   (No external ClickSend client required for local Hubtel; ensure your local service implements `/send` and `/status` endpoints.)

- Local testing and development without touching a third-party SMS provider
- Easier experimentation with alphanumeric sender IDs for small organizations
- Lightweight: you control the service and logs

## Hubtel vs Twilio Differences

### Practical benefits of Hubtel (local SMS holder):
- Local testing and development without touching a third-party SMS provider
- Easier experimentation with alphanumeric sender IDs for small organizations
- Lightweight: you control the service and logs
- Local testing and development without touching a third-party SMS provider
- Easier experimentation with alphanumeric sender IDs for small organizations
- Lightweight: you control the service and logs

### API differences:
- Huibtel is a local HTTP-based endpoint (POST /send, GET /status/<id>)
- Twilio is a hosted provider with account-level credentials and phone numbers

### Features:
- Huibtel is ideal for on-prem or staged deployments and fast iteration
- For production at scale, consider a hosted SMS gateway or provider that supports approved alphanumeric sender IDs in your target countries

## Troubleshooting

### Common Issues:

1. **Local service not reachable**
   - Ensure `HUBTEL_API_URL` points to a running Hubtel-compatible service and is reachable from the Django app.

2. **Authentication Failed**
   - If your Hubtel service requires an API key, set `HUBTEL_API_KEY` in `.env` and verify it matches the service configuration.

3. **SMS Not Sending**
   - Ensure phone numbers include country code (e.g., +233501234567)
   - Check your Hubtel service logs for errors and verify the service endpoints `/send` and `/status/<id>` behave as expected

4. **Database Migration Issues**
   - Run `python manage.py makemigrations` first
   - Then run `python manage.py migrate`

### Testing Commands:

```bash
# Test Hubtel API connection
python manage.py shell

# In Django shell:
from core.hubtel_utils import send_sms
from core.models import School

school = School.objects.first()
send_sms('+233501234567', 'Test message', school)
```

## Support

-- Huibtel/local SMS service: your local service docs or implementation
- Django Migration Guide: https://docs.djangoproject.com/en/stable/topics/migrations/

## Security Notes

- Keep your ClickSend API key secure
- Use environment variables for credentials
- Consider rotating API keys periodically
- Monitor usage in ClickSend dashboard