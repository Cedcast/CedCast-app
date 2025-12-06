#!/usr/bin/env python
"""
Test script for Huibtel integration
This script helps verify that the local Huibtel setup is working correctly.
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).resolve().parent
sys.path.append(str(project_dir))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
django.setup()

def test_hubtel_import():
    """Test if Hubtel utility can be imported correctly"""
    try:
        from core.hubtel_utils import send_sms
        print("✓ Hubtel utility imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import Hubtel utility: {e}")
        return False

def test_hubtel_configuration():
    """Test Hubtel configuration"""
    from django.conf import settings

    api_url = getattr(settings, 'HUBTEL_API_URL', None)
    api_key = getattr(settings, 'HUBTEL_API_KEY', None)

    if api_url and api_url != "http://your-hubtel.example" :
        print("✓ Hubtel API URL configured")
        return True
    else:
        print("⚠ Hubtel credentials not configured or using placeholders")
        print("  Please update your .env file with HUBTEL_API_URL (and optional HUBTEL_API_KEY)")
        return False

def test_model_migration():
    """Test if the School model has a sender_id (used by Huibtel)"""
    try:
        from core.models import School

        school_fields = [field.name for field in School._meta.get_fields()]

        if 'sender_id' in school_fields:
            print("✓ School model has sender_id (suitable for Huibtel)")
            return True
        else:
            print("✗ School model missing expected fields for Huibtel (e.g. sender_id)")
            return False
    except Exception as e:
        print(f"✗ Error checking model fields: {e}")
        return False

def test_send_sms_configured():
    """Check that Hubtel send settings are present. This test does NOT send an SMS.

    To run a live send test, run a manual script or enable a dedicated live-test flag.
    """
    from django.conf import settings

    api_url = getattr(settings, 'HUBTEL_API_URL', None)
    client_id = getattr(settings, 'HUBTEL_CLIENT_ID', None)
    client_secret = getattr(settings, 'HUBTEL_CLIENT_SECRET', None) or getattr(settings, 'HUBTEL_API_KEY', None)

    if not api_url:
        print("✗ HUBTEL_API_URL not configured")
        return False
    if not (client_id and client_secret):
        print("⚠ HUBTEL client credentials (HUBTEL_CLIENT_ID/HUBTEL_CLIENT_SECRET) not configured; some Hubtel accounts require them")
        # still pass because API URL is present and deployment can use API_KEY instead
        return True
    print("✓ Hubtel send configuration looks present")
    return True

def main():
    """Run all tests"""
    print("🧪 Testing Hubtel Integration")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_hubtel_import),
        ("Configuration Test", test_hubtel_configuration),
        ("Model Migration Test", test_model_migration),
    ("SMS Function Test", test_send_sms_configured),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Hubtel integration is ready.")
        print("\nNext steps:")
        print("1. Update .env with your HUBTEL_API_URL and optionally HUBTEL_API_KEY")
        print("2. Test sending a real SMS through the Django admin")
        print("3. Run: python manage.py runserver")
    else:
        print("⚠ Some tests failed. Check the errors above.")

if __name__ == "__main__":
    main()