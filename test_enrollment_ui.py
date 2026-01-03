"""
Test enrollment request UI and API interaction
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_alert_system.settings')
django.setup()

from django.test import TestCase, Client
from django.urls import reverse
from core.models import User, EnrollmentRequest
from django.utils import timezone

class EnrollmentRequestTests(TestCase):
    def setUp(self):
        # Create a superadmin user
        self.admin = User.objects.create_user(
            username='admin_test',
            password='testpass123',
            email='admin@test.com',
            role=User.SUPER_ADMIN
        )
        
        # Create test enrollment requests
        self.pending_req = EnrollmentRequest.objects.create(
            org_name='Test Org',
            org_type='school',
            contact_name='Test User',
            position='Manager',
            email='test@org.com',
            phone='+233501234567',
            status='pending'
        )
        
        self.client = Client()
        self.client.force_login(self.admin)
    
    def test_dashboard_access(self):
        """Test that superadmin can access the dashboard"""
        response = self.client.get(reverse('super_admin'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enrollment Management')
        print("✓ Dashboard access works")
    
    def test_approval_via_api(self):
        """Test approval via API endpoint"""
        response = self.client.post(
            reverse('approve_enrollment', args=[self.pending_req.id]),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify status changed
        self.pending_req.refresh_from_db()
        self.assertEqual(self.pending_req.status, 'approved')
        self.assertEqual(self.pending_req.reviewed_by, self.admin)
        print("✓ Approval via API works")
    
    def test_rejection_via_api(self):
        """Test rejection via API endpoint"""
        response = self.client.post(
            reverse('reject_enrollment', args=[self.pending_req.id]),
            {'reason': 'Test rejection reason'}
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify status changed
        self.pending_req.refresh_from_db()
        self.assertEqual(self.pending_req.status, 'rejected')
        self.assertEqual(self.pending_req.review_notes, 'Test rejection reason')
        print("✓ Rejection via API works")
    
    def test_enrollment_details_api(self):
        """Test getting enrollment request details"""
        response = self.client.get(
            reverse('enrollment_request_details', args=[self.pending_req.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['request']['id'], self.pending_req.id)
        self.assertEqual(data['request']['org_name'], 'Test Org')
        print("✓ Enrollment details API works")

if __name__ == '__main__':
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(EnrollmentRequestTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n✓ All enrollment tests passed!")
    else:
        print(f"\n✗ {len(result.failures)} tests failed")
