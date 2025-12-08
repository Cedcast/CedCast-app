Overview
========
This document describes the high-level architecture of the CedCast SaaS multi-tenant SMS platform (CedCast-app). It includes an ASCII component diagram, the main data flows (Send Now, Schedule + Worker), provider fallback behavior, secrets handling, and deployment/operations notes.

ASCII Architecture Diagram
==========================
Browser / Admin UIs
 (Tenant Admin / Super Admin / Support Admin)
       |
       |  HTTPS (forms, send/schedule requests, admin pages)
       v
 +---------------------------------------+
 | Django web app (school_alert_system)  |
 | - core app (models, views, templates) |
 | - provider utils: hubtel_utils,       |
 |   clicksend_utils, twilio_utils       |
 | - crypto utils (encrypt/decrypt)      |
 | - management commands (worker)        |
 +----+----------------------------------+
      |                     |            
      | DB (SQLite/Postgres)|  Background worker (management command)
      |                     v
      |                 +---------------------------------+
      |                 | send_pending_org_messages CMD   |
      |                 | - polls pending OrgAlertRecipient| 
      |                 | - calls provider utils (Hubtel) |
      |                 | - fallback to ClickSend if fail |
      |                 +---------------------------------+
      v
 +-------------+
 | Database    |
 | (db.sqlite3)|
 +-------------+
      |
  | stores models: Tenant / Organization (per-tenant creds),
  | Contact, ContactGroup, TenantMessage, TenantAlertRecipient, User
      v
 +-------------------------+
 | External SMS Providers  |
 |  - Hubtel (primary)     |
 |  - ClickSend (fallback) |
 |  - Twilio (legacy/opt)  |
 +-------------------------+
      ^
      | (HTTP API calls from provider utils)
      | (Delivery receipts via webhooks optional)
      v
 +-------------------------+
 | Optional: Webhook Receiver|
 | - /hubtel/webhook/        |
 | - updates OrgAlertRecipient.provider_status
 +-------------------------+

Legend
------
- Solid arrows: synchronous HTTP/DB calls.
- Worker: scheduled or cron-driven management command that processes pending recipients.
- Provider utils: small wrappers that read decrypted per-tenant or global credentials and call external provider APIs.

Core Components
---------------
-- core/models.py
  - Tenant / Organization: stores per-tenant credentials (clicksend_username, clicksend_api_key, hubtel_api_url, hubtel_client_id, hubtel_client_secret, hubtel_sender_id, sender_id). Secrets are stored encrypted.
  - Contact, ContactGroup: org contacts and groups for targeting.
  - Contact, ContactGroup: tenant contacts and groups for targeting.
  - TenantMessage (OrgMessage): a message entity (content, scheduled_time, sent flag).
  - TenantAlertRecipient (OrgAlertRecipient): per-recipient status, provider_message_id, provider_status, retry_count.
  - User: custom user with role field (SUPER_ADMIN, TENANT_ADMIN, SUPPORT_ADMIN). Existing SCHOOL_ADMIN role can be migrated to TENANT_ADMIN if desired.

-- core/views.py
  - `org_send_sms` / `tenant_send_sms`: tenant admin send page. Creates TenantMessage and TenantAlertRecipient rows. Supports send_now (synchronous) and schedule (create pending rows).
  - `super_edit_org_view`: edit per-tenant credentials (super-admin only) — stores encrypted secrets.

- core/hubtel_utils.py, core/clicksend_utils.py, core/twilio_utils.py
  - Wrap external provider APIs. They read credentials from Organization (tenant) or Django settings, decrypt values via `core/utils/crypto_utils.py` and call the provider.
  - Hubtel is implemented as the primary provider; clicksend is fallback.
  - Both support "dry-run" flags for testing (settings.HUBTEL_DRY_RUN / CLICKSEND_DRY_RUN).

- core/utils/crypto_utils.py
  - Provides encrypt_value(/decrypt_value) using Fernet (if `cryptography` installed) or Django signing as fallback.
  - Encrypted values saved with a prefix (e.g., "ENC::...").

-- Management command: `send_pending_org_messages`
  - Finds pending TenantAlertRecipient assigned to TenantMessage.scheduled_time <= now.
  - Attempts send using Hubtel -> ClickSend fallback.
  - Updates provider_message_id, status, sent_at, error_message, retry_count.
  - `--dry-run` option available for safe testing (optional).

Data Flows (SaaS tenant view)
----------
1) "Send Now" (UI synchronous path)
   - Org admin POSTs message form with action=send_now.
  - Tenant admin POSTs message form with action=send_now.
  - `tenant_send_sms` / `org_send_sms` view creates TenantMessage + TenantAlertRecipient rows then loops recipients:
     - Calls `hubtel_utils.send_sms(phone, body, org)`.
     - On exception, calls `clicksend_utils.send_sms(...)`.
     - On success: sets recipient.status='sent', provider_message_id, sent_at.
     - On repeated failures: marks recipient as 'failed' or leaves 'pending' for retries.
   - If no pending recipients remain, the message.sent flag is set True.

2) "Schedule" (deferred send)
   - Org admin POSTs with scheduled_time set or action=schedule.
  - Tenant admin POSTs with scheduled_time set or action=schedule.
  - `tenant_send_sms` creates TenantMessage + TenantAlertRecipient rows with status='pending'.
   - A scheduler (cron/systemd timer or Celery) runs `send_pending_org_messages` regularly.
   - Worker picks pending rows and runs the same provider-fallback logic.

3) Delivery status updates
   - Provider returns a provider_message_id when accepted.
   - Delivery receipts can be received via webhooks (if provider supports) to update provider_status on OrgAlertRecipient.
   - Or the app can poll provider APIs for delivery status using `get_sms_delivery_status` helpers.

Secrets & Encryption
--------------------
-- Per-tenant credentials are stored on the `Tenant`/`Organization` model. When saving via the super-admin UI the values are encrypted using `crypto_utils.encrypt_value()`.
-- Provider utils call `crypto_utils.decrypt_value()` before using credentials.
-- Environment variables expected (SaaS):
  - HUBTEL_API_URL, HUBTEL_CLIENT_ID, HUBTEL_CLIENT_SECRET, HUBTEL_API_KEY
  - CLICKSEND_USERNAME, CLICKSEND_API_KEY
  - HUBTEL_DRY_RUN and CLICKSEND_DRY_RUN for safe testing
  - SMS_ENCRYPTION_KEY (optional) to control Fernet key

Deployment notes (SaaS)
----------------
-- Local dev: `DEBUG=True` and sqlite (db.sqlite3) is convenient for development. Be careful with live provider creds in local env.
-- Production: use DATABASE_URL (Postgres) and configure secret env vars. For SaaS deployments you will also need to plan tenant provisioning, isolation, and backup strategies.
- Worker scheduling options:
  - Simple: run `send_pending_org_messages` from a cron or systemd timer every minute.
  - Scalable: move to Celery + Redis with a periodic task and concurrency for higher throughput.

Operational considerations (SaaS)
------------------------
-- Observability: log provider responses and HTTP statuses. Keep request/response IDs and add tenant id metadata for per-tenant metrics.
-- Retry/backoff: worker uses retry_count; consider exponential backoff and a dead-letter queue for persistent failures.
-- Rate limits / throttling: SaaS multi-tenant platforms must enforce per-tenant and global rate limits. Add batching, rate-limiters, and throttling policies.
-- Secrets: prefer a managed secret store (Vault, AWS Secrets Manager) in production and avoid storing long-lived plaintext creds in dev environments.
-- Webhooks: set up provider webhook endpoints to reliably mark delivery statuses; protect with HMAC using HUBTEL_WEBHOOK_SECRET. Store raw webhook events for audit.

Suggested improvements (SaaS transition)
----------------------------------
1. Rename and audit models and views to use 'Tenant' terminology (or keep Organization as alias) and provide migration guidance.
2. Replace or extend role constants: add TENANT_ADMIN / SUPPORT_ADMIN, and map existing SCHOOL_ADMIN where relevant.
3. Add per-tenant rate limiting, quotas, and usage metrics for billing.
4. Add tenant onboarding APIs (signup, invite flow) and admin dashboard for tenant settings and billing hooks.
5. Add tests and CI checks for multi-tenant behavior (isolation, data access control).
6. Add webhook event store and admin UI for raw payloads and retries.

Files of interest
-----------------
- `core/models.py` — main data model definitions (Tenant/Organization, Contact, TenantMessage, TenantAlertRecipient, User).
- `core/views.py` — tenant send view and super admin tenant edit.
- `core/hubtel_utils.py` — Hubtel provider implementation.
- `core/clicksend_utils.py` — ClickSend implementation.
- `core/management/commands/send_pending_org_messages.py` — worker command.
- `core/utils/crypto_utils.py` — encryption helpers.

Contact
-------
If you want, I can also generate a PNG/SVG diagram (graphviz) representation and add it to the repo (requires graphviz to be installed). Would you like a rendered image version as well?
