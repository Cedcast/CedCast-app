#!/usr/bin/env python3
"""
Post-deploy smoke test helpers.

Usage: set environment variables and run this script from your local machine or Render console.

Environment variables:
- RENDER_URL: the public URL of your deployed site (e.g. https://my-service.onrender.com)
- TEST_PHONE: optional phone number to send a test SMS to (in +233... format)
- RUN_SEND: if '1' will attempt to send an SMS using HUBTEL settings (use with care)
- SIMULATE_WEBHOOK: if '1' will POST a signed webhook payload to the deployed /webhooks/hubtel/

This script can be used after deployment to verify:
- the webhook endpoint is reachable and accepts a signed payload
- (optionally) sending an SMS works and Hubtel returns a messageId

Note: this script expects environment variables for HUBTEL_* to be configured on the host
where it runs (or in Render console one-off job).
"""
import os
import sys
import json
import hmac
import hashlib
import requests

RENDER_URL = os.environ.get('RENDER_URL')
TEST_PHONE = os.environ.get('TEST_PHONE')
RUN_SEND = os.environ.get('RUN_SEND') == '1'
SIMULATE_WEBHOOK = os.environ.get('SIMULATE_WEBHOOK') == '1'
WEBHOOK_SECRET = os.environ.get('HUBTEL_WEBHOOK_SECRET')

if not RENDER_URL:
    print('Please set RENDER_URL environment variable to your service URL, e.g. https://my-app.onrender.com')
    sys.exit(1)

print('Using RENDER_URL=', RENDER_URL)

if RUN_SEND and TEST_PHONE:
    print('Attempting test send to', TEST_PHONE)
    # Import Django app helpers when running inside the project environment
    try:
        sys.path.insert(0, os.getcwd())
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
        django.setup()
        from core import hubtel_utils
        # Use a simple text
        mid = hubtel_utils.send_sms(TEST_PHONE, 'Render post-deploy test message. Please ignore.', None)
        print('Send result messageId=', mid)
    except Exception as e:
        print('Send failed:', e)

if SIMULATE_WEBHOOK:
    if not WEBHOOK_SECRET:
        print('HUBTEL_WEBHOOK_SECRET is not set; cannot sign webhook payload')
        sys.exit(1)
    # Build a fake payload with a placeholder messageId
    payload = {'messageId': 'smoke-test-' + hashlib.sha1(RENDER_URL.encode()).hexdigest()[:8], 'status': 'Delivered', 'to': TEST_PHONE}
    body = json.dumps(payload).encode('utf-8')
    sig = hmac.new(WEBHOOK_SECRET.encode('utf-8'), body, hashlib.sha256).hexdigest()
    headers = {'Content-Type': 'application/json', 'X-Hubtel-Signature': sig}
    url = RENDER_URL.rstrip('/') + '/webhooks/hubtel/'
    print('Posting simulated webhook to', url)
    try:
        r = requests.post(url, data=body, headers=headers, timeout=10)
        print(' ->', r.status_code, r.text[:1000])
    except Exception as e:
        print(' -> HTTP error:', e)

print('\nSmoke tests complete. If you want me to run these after your Render deploy, tell me the service URL and whether to run send/webhook tests.')
