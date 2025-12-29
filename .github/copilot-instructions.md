# Copilot Instructions for CedCast-app

Purpose: Help AI agents work productively in this Django multi-tenant SMS platform by explaining the architecture, workflows, conventions, and integration points that matter here.

## Big Picture
- Django 5 project with main app `core` under project `school_alert_system`.
- Multi-tenant via `Organization` (aka tenant). Users have roles: SUPER_ADMIN, SCHOOL_ADMIN, ORG_ADMIN.
- SMS sending: Hubtel is primary, ClickSend is fallback, Twilio is legacy.
- Two send paths:
  - Sync "send now" from views: creates `OrgMessage` + `OrgAlertRecipient` and sends inline.
  - Deferred via scheduler/worker: creates rows with status `pending` and background commands send when due.

## Key Files
- Models and roles: core/models.py (Organization, OrgMessage, OrgAlertRecipient, User).
- Views and flows: core/views.py (login with optional reCAPTCHA, org send/schedule, admin dashboards, Paystack billing callbacks).
- Provider integrations: core/hubtel_utils.py (primary), core/clicksend_utils.py (fallback), core/twilio_utils.py (legacy).
- Worker & scheduling: core/management/commands/
  - send_pending_org_messages.py (pending recipients + retry/fallback)
  - send_scheduled_org_messages.py and send_scheduled_messages.py (scheduled sends)
  - run_scheduler.py (loops commands; use for background service)
- Secrets/crypto: core/utils/crypto_utils.py (ENC:: prefix, Fernet or Django signing fallback).
- Settings & env: school_alert_system/settings.py (DB, cache, reCAPTCHA, Hubtel, Paystack, static files).

## Running Locally
- Migrate and start server:
  - `python manage.py migrate`
  - `python manage.py createsuperuser` (optional)
  - `python manage.py runserver`
- Background sending (choose one):
  - Ad-hoc: `python manage.py send_pending_org_messages --limit 200`
  - Looping worker: `python manage.py run_scheduler --interval 60 --limit 200`
- Tests:
  - `python manage.py test` (template compile validation, Paystack callback tests with mocks in core/tests/).

## Environment & Config (subset)
- Hubtel: `HUBTEL_API_URL`, `HUBTEL_CLIENT_ID`, `HUBTEL_CLIENT_SECRET`, `HUBTEL_DEFAULT_SENDER`, `HUBTEL_WEBHOOK_SECRET`, `HUBTEL_DRY_RUN`.
- ClickSend (fallback): `CLICKSEND_USERNAME`, `CLICKSEND_API_KEY`.
- Optional: `RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY` (enforced on login pages if secret present).
- Payments: `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY`.
- DB: `DATABASE_URL` (Postgres in prod), else sqlite when `DEBUG=True`.
- Cache: `REDIS_URL` enables Redis; else DB cache (`cache_table`).
- Encryption: `SMS_ENCRYPTION_KEY` (optional; otherwise derived from `SECRET_KEY`).

## Patterns & Conventions
- Credentials stored encrypted on the tenant/org using `encrypt_value()`; decrypt with `decrypt_value()` before use. Encoded values start with `ENC::`.
- Provider call pattern (prefer Hubtel, fallback to ClickSend on failure):
  - `hubtel_utils.send_sms(phone, body, tenant)` returns a provider message id string.
  - Worker updates `OrgAlertRecipient.provider_message_id`, `status`, `sent_at`, with retry/backoff via `retry_count`.
- Time handling for schedules: normalize naive datetimes to aware using `timezone.make_aware` before comparisons.
- Caching: use the cache keys/timeouts from constants/settings (e.g., dashboard/contacts).
- UI templates: compiled by tests to catch template errors early.

## External Interfaces
- Hubtel send: GET to `HUBTEL_API_URL` with params `(clientid, clientsecret, from?, to, content)`; returns message id (JSON or text). Status endpoint optional.
- Webhooks: Configure Hubtel webhook to `/webhooks/hubtel/` and validate with `HUBTEL_WEBHOOK_SECRET` (see deployment notes).
- Paystack: `core/paystack_utils.py` handles init/verify; org billing callback view updates balances and records `Payment`.

## Common Tasks
- Seed demo data: `python manage.py seed_demo_org`, `seed_sms_templates` (see management/commands/).
- Retry failures: `python manage.py retry_failed_org_messages`.
- Promote users or bootstrap superadmin: `ensure_superadmin`, `promote_user`, `create_super_admin`.

## Deployment Notes
- Render: see render.yaml and DEPLOY_RENDER.md for env vars, static files (WhiteNoise), and post-deploy steps (`migrate`, create superuser). Configure webhook after URL is live.

Tip: When adding provider features, keep tenant-specific creds encrypted in models, expose minimal settings in env, and route all sends through provider utils to preserve fallback and audit semantics.
