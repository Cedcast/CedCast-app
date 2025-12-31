from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model


class SuperAdminPagesTests(TestCase):
	def setUp(self):
		User = get_user_model()
		# create a super-admin user
		self.super = User.objects.create_user(username='test_super', password='password123')
		# ensure role is set explicitly
		self.super.role = User.SUPER_ADMIN
		self.super.save()
		# create a regular school admin user
		self.regular = User.objects.create_user(username='test_user', password='password123')
		self.regular.role = User.SCHOOL_ADMIN
		self.regular.save()

	def test_super_can_access_super_admin_pages(self):
		# Force login with explicit backend to ensure session auth in tests
		self.client.force_login(self.super, backend='django.contrib.auth.backends.ModelBackend')
		resp = self.client.get(reverse('onboarding'), follow=True)
		self.assertEqual(resp.status_code, 200)
		resp = self.client.get(reverse('system_logs'), follow=True)
		self.assertEqual(resp.status_code, 200)
		resp = self.client.get(reverse('global_templates'), follow=True)
		self.assertEqual(resp.status_code, 200)

	def test_non_super_is_redirected(self):
		self.client.force_login(self.regular, backend='django.contrib.auth.backends.ModelBackend')
		resp = self.client.get(reverse('onboarding'))
		# non-super should be redirected to dashboard
		self.assertIn(resp.status_code, (302, 301))
		resp = self.client.get(reverse('system_logs'))
		self.assertIn(resp.status_code, (302, 301))
		resp = self.client.get(reverse('global_templates'))
		self.assertIn(resp.status_code, (302, 301))