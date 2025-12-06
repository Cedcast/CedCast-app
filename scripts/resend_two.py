#!/usr/bin/env python3
import os
import sys
import django
import time
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from django.utils import timezone
from core.models import School, Parent, Message, AlertRecipient
from core import hubtel_utils

numbers = ['+233558876737', '+233593033895', '+233530422137']
polished = ("Test: Default School — Please ignore this message. "
           "This is a short delivery test to check message routing.")

school, _ = School.objects.get_or_create(slug='default-school', defaults={'name': 'Default School'})
print('Using school:', school.name)
msg = Message.objects.create(school=school, content=polished, scheduled_time=timezone.now())
print('Created Message id=', msg.id)

results = []
for i, num in enumerate(numbers, start=1):
    print(f"Sending to {num} ({i}/{len(numbers)})...")
    parent, created = Parent.objects.get_or_create(school=school, phone_number=num, defaults={'name': f'Auto Test Recipient {i}'})
    ar = AlertRecipient.objects.create(message=msg, parent=parent, status='pending')
    start = time.time()
    try:
        mid = hubtel_utils.send_sms(parent.phone_number, msg.content, school)
        elapsed = time.time() - start
        print(f" -> sent in {elapsed:.1f}s, messageId={mid}")
        ar.provider_message_id = mid
        ar.status = 'sent'
        ar.sent_at = timezone.now()
        ar.error_message = ''
        ar.save()
        results.append((num, 'sent', mid, ''))
    except Exception as e:
        elapsed = time.time() - start
        em = str(e)
        safe_err = re.sub(r"(clientsecret|clientid)=[^&\\s]+", r"\1=<REDACTED>", em)
        print(f" -> failed in {elapsed:.1f}s: {safe_err[:200]}")
        ar.status = 'failed'
        ar.error_message = em[:2000]
        ar.save()
        results.append((num, 'failed', None, safe_err[:500]))

if any(r[1] == 'sent' for r in results):
    msg.sent = True
    msg.save()

print('\nSummary:')
for num, status, mid, err in results:
    print('-', num, '|', status, '| id=', mid or 'N/A', ('| err=' + err) if err else '')
