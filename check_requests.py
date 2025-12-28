#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
sys.path.insert(0, '/home/packnet777/SCHOOL PROJECT')
django.setup()

from core.models import EnrollmentRequest
from django.utils import timezone

# Check existing requests
pending = EnrollmentRequest.objects.filter(status='pending')
approved = EnrollmentRequest.objects.filter(status='approved')
rejected = EnrollmentRequest.objects.filter(status='rejected')

print(f"Pending requests: {pending.count()}")
print(f"Approved requests: {approved.count()}")
print(f"Rejected requests: {rejected.count()}")

# Create a test pending request if none exist
if pending.count() == 0:
    print("\nCreating a test pending enrollment request...")
    test_request = EnrollmentRequest.objects.create(
        org_name="Test Company Inc",
        org_type="company",
        address="123 Test Street, Test City",
        contact_name="John Doe",
        position="CEO",
        email="john@testcompany.com",
        phone="+1234567890",
        message="We are interested in your SMS platform for our business communications.",
        status='pending'
    )
    print(f"Created test request: {test_request.org_name} (ID: {test_request.id})")

# Show sample requests
pending = EnrollmentRequest.objects.filter(status='pending')
if pending.count() > 0:
    print("\nPending requests:")
    for req in pending:
        print(f"  - {req.org_name} ({req.contact_name}) - Created: {req.created_at}")

if approved.count() > 0:
    print("\nApproved requests:")
    for req in approved[:3]:
        print(f"  - {req.org_name} ({req.contact_name}) - Reviewed: {req.reviewed_at}")

if rejected.count() > 0:
    print("\nRejected requests:")
    for req in rejected[:3]:
        print(f"  - {req.org_name} ({req.contact_name}) - Reviewed: {req.reviewed_at}")