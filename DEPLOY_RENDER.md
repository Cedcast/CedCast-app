Render deployment checklist

1. Connect your Git repo to Render and create a new Web Service.
   - Use the `render.yaml` in the repo (Render will pick it up automatically) or configure via the dashboard.

2. Environment variables (set these in the Render service settings):
   - DJANGO_SETTINGS_MODULE=school_alert_system.settings
   - SECRET_KEY=your-production-secret
   - DEBUG=False
   - ALLOWED_HOSTS=.onrender.com (or your custom domain)
   - DATABASE_URL (if using Render Postgres)
   - HUBTEL_API_URL=https://smsc.hubtel.com/v1/messages/send
   - HUBTEL_CLIENT_ID=...
   - HUBTEL_CLIENT_SECRET=...
   - HUBTEL_DEFAULT_SENDER=233XXXXXXXXX
   - HUBTEL_WEBHOOK_SECRET=super-secret-random-string
   - HUBTEL_DRY_RUN=false

3. Database
   - Add a Render PostgreSQL service and attach it to this service (optional but recommended).
   - After first deploy, run:
     - python manage.py migrate
     - python manage.py createsuperuser (optional)

4. Static files
   - WhiteNoise is enabled in `settings.py`. The build step runs `collectstatic`.

5. Webhook
   - After the service URL is available, set Hubtel webhook to:
     https://<your-service>.onrender.com/webhooks/hubtel/
   - Set the webhook secret in Hubtel to the same value as `HUBTEL_WEBHOOK_SECRET`.

6. Post-deploy smoke tests (I can run these for you):
   - Send a test SMS and confirm messageId returned.
   - Poll the Hubtel status endpoint for the messageId and check status.
   - Wait for DLR or simulate a signed webhook to ensure DB updates.

Notes
- If you plan to use attachments or large media, consider using S3 for media storage and set MEDIA_URL accordingly.
