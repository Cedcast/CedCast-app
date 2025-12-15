from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Organization, Payment
from decimal import Decimal
from unittest.mock import patch, MagicMock


class PaymentCallbackTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.organization = Organization.objects.create(
            name='Test Org',
            slug='test-org',
            balance=Decimal('10.00'),
            is_active=True
        )
        self.user.organization = self.organization
        self.user.role = 'org_admin'
        self.user.save()

    @patch('core.paystack_utils.verify_payment')
    def test_post_callback_successful_payment(self, mock_verify):
        """Test POST callback with successful payment updates balance"""
        mock_verify.return_value = {
            'data': {
                'status': 'success',
                'amount': 50000,  # 500.00 GHS in pesewas
                'id': 'test_txn_123'
            }
        }

        response = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {'reference': 'test_ref_123'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['balance'], '510.00')  # 10.00 + 500.00

        # Check database state
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.balance, Decimal('510.00'))

        payment = Payment.objects.get(paystack_reference='test_ref_123')
        self.assertEqual(payment.amount, Decimal('500.00'))
        self.assertEqual(payment.status, 'success')

    @patch('core.paystack_utils.verify_payment')
    def test_post_callback_duplicate_reference(self, mock_verify):
        """Test POST callback with duplicate reference doesn't double-update"""
        mock_verify.return_value = {
            'data': {
                'status': 'success',
                'amount': 25000,  # 250.00 GHS
                'id': 'test_txn_456'
            }
        }

        # First call
        response1 = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {'reference': 'test_ref_456'}
        )
        self.assertEqual(response1.status_code, 200)

        # Second call with same reference
        response2 = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {'reference': 'test_ref_456'}
        )
        self.assertEqual(response2.status_code, 200)

        # Balance should only be updated once
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.balance, Decimal('260.00'))  # 10.00 + 250.00

        # Only one payment record
        payments = Payment.objects.filter(paystack_reference='test_ref_456')
        self.assertEqual(payments.count(), 1)

    @patch('core.paystack_utils.verify_payment')
    def test_post_callback_failed_payment(self, mock_verify):
        """Test POST callback with failed payment creates failed record"""
        mock_verify.return_value = {
            'data': {
                'status': 'failed',
                'amount': 10000,  # 100.00 GHS
                'id': 'test_txn_789'
            }
        }

        response = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {'reference': 'test_ref_789'}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['status'], 'failed')

        # Balance should not change
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.balance, Decimal('10.00'))

        # Failed payment record should exist
        payment = Payment.objects.get(paystack_reference='test_ref_789')
        self.assertEqual(payment.status, 'failed')

    @patch('core.paystack_utils.verify_payment')
    def test_post_callback_verification_error(self, mock_verify):
        """Test POST callback handles verification exceptions"""
        mock_verify.side_effect = Exception("Paystack API error")

        response = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {'reference': 'test_ref_error'}
        )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Paystack API error', data['message'])

    def test_post_callback_missing_reference(self):
        """Test POST callback without reference returns error"""
        response = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'test-org'}),
            {}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Missing payment reference', data['message'])

    def test_callback_invalid_org_slug(self):
        """Test callback with invalid org slug"""
        response = self.client.post(
            reverse('org_billing_callback', kwargs={'org_slug': 'invalid-org'}),
            {'reference': 'test_ref'}
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Organization not found', data['message'])