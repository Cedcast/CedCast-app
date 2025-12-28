from django.db import models
from django.contrib.auth.models import AbstractUser
from decimal import Decimal

class AlertRecipient(models.Model):
	message = models.ForeignKey('Message', on_delete=models.CASCADE, related_name='recipients_status')
	parent = models.ForeignKey('Parent', on_delete=models.CASCADE)
	status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], default='pending')
	# ID returned by the SMS provider (Hubtel messageId)
	provider_message_id = models.CharField(max_length=255, blank=True, null=True)
	# Provider-specific delivery status (raw value from provider)
	provider_status = models.CharField(max_length=100, blank=True, null=True)
	sent_at = models.DateTimeField(blank=True, null=True)
	error_message = models.TextField(blank=True, null=True)

	class Meta:
		indexes = [
			models.Index(fields=['status', 'sent_at']),
			models.Index(fields=['message', 'status']),
		]

	def __str__(self):
		return f"{self.parent.name} - {self.status}"

class SMSTemplate(models.Model):
	school = models.ForeignKey('School', on_delete=models.CASCADE)
	name = models.CharField(max_length=100)
	content = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.name} ({self.school.name})"


class OrgSMSTemplate(models.Model):
	organization = models.ForeignKey('Organization', on_delete=models.CASCADE)
	name = models.CharField(max_length=100)
	content = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)
	is_pre_built = models.BooleanField(default=False, help_text="Whether this is a pre-built template")

	def __str__(self):
		return f"{self.name} ({self.organization.name})"

class School(models.Model):
	name = models.CharField(max_length=255)
	logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
	address = models.TextField(blank=True, null=True)
	phone_primary = models.CharField(max_length=20, blank=True, null=True)
	phone_secondary = models.CharField(max_length=20, blank=True, null=True)
	primary_color = models.CharField(max_length=7, default="#000000")  # HEX color
	secondary_color = models.CharField(max_length=7, default="#FFFFFF")
	slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)
	# ClickSend SMS configuration
	clicksend_username = models.CharField(max_length=100, blank=True, null=True)
	clicksend_api_key = models.CharField(max_length=100, blank=True, null=True)
	sender_id = models.CharField(max_length=20, blank=True, null=True, help_text="Optional alphanumeric sender ID (requires approval)")
	# Legacy Twilio fields (will be removed in future migration)
	twilio_account_sid = models.CharField(max_length=64, blank=True, null=True)
	twilio_auth_token = models.CharField(max_length=64, blank=True, null=True)
	twilio_phone_number = models.CharField(max_length=20, blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name

class User(AbstractUser):
	SUPER_ADMIN = "super_admin"
	SCHOOL_ADMIN = "school_admin"
	ORG_ADMIN = "org_admin"
	ROLE_CHOICES = [
		(SUPER_ADMIN, "Super Admin"),
		(SCHOOL_ADMIN, "School Admin"),
		(ORG_ADMIN, "Organization Admin"),
	]
	role = models.CharField(max_length=20, choices=ROLE_CHOICES)
	school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
	organization = models.ForeignKey('Organization', on_delete=models.CASCADE, null=True, blank=True)


class Parent(models.Model):
	school = models.ForeignKey(School, on_delete=models.CASCADE)
	name = models.CharField(max_length=255)
	phone_number = models.CharField(max_length=20)

	def clean(self):
		from django.core.exceptions import ValidationError
		if not self.phone_number.startswith('+233'):
			raise ValidationError({'phone_number': 'Phone number must start with +233 (Ghana country code). Example: +233501234567'})

	def save(self, *args, **kwargs):
		self.full_clean()
		super().save(*args, **kwargs)
	fee_status = models.CharField(max_length=50, default="paid")  # e.g., paid, late
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.name} ({self.phone_number})"

class Ward(models.Model):
	school = models.ForeignKey(School, on_delete=models.CASCADE)
	parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name="wards")
	name = models.CharField(max_length=255)
	student_class = models.CharField(max_length=50, blank=True, null=True)  # e.g., JHS3
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.name} (Ward of {self.parent.name})"

class Message(models.Model):
	school = models.ForeignKey(School, on_delete=models.CASCADE)
	content = models.TextField()
	scheduled_time = models.DateTimeField()
	sent = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
	recipients = models.ManyToManyField('Parent', through='AlertRecipient', related_name='messages')

	class Meta:
		indexes = [
			models.Index(fields=['school', 'scheduled_time']),
			models.Index(fields=['school', 'sent', 'created_at']),
		]

	def __str__(self):
		return f"Message to {self.school.name} at {self.scheduled_time}"


class OrgMessage(models.Model):
	organization = models.ForeignKey('Organization', on_delete=models.CASCADE)
	content = models.TextField()
	scheduled_time = models.DateTimeField()
	sent = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)

	class Meta:
		indexes = [
			models.Index(fields=['organization', 'scheduled_time']),
			models.Index(fields=['organization', 'sent', 'created_at']),
			models.Index(fields=['organization', 'created_at']),
		]

	def get_recipients_count(self):
		"""Get total number of recipients for this message"""
		return self.orgalertrecipient_set.count()

	def get_sent_recipients_count(self):
		"""Get number of successfully sent recipients"""
		return self.orgalertrecipient_set.filter(status='sent').count()

	def get_failed_recipients_count(self):
		"""Get number of failed recipients"""
		return self.orgalertrecipient_set.filter(status='failed').count()

	def get_pending_recipients_count(self):
		"""Get number of pending recipients"""
		return self.orgalertrecipient_set.filter(status='pending').count()

	def get_delivery_rate(self):
		"""Calculate delivery rate for this message"""
		total = self.get_recipients_count()
		sent = self.get_sent_recipients_count()
		return (sent / total * 100) if total > 0 else 0

	def mark_as_sent(self):
		"""Mark message as sent"""
		self.sent = True
		self.save(update_fields=['sent'])

	def create_recipients(self, contacts):
		"""Create OrgAlertRecipient instances for the given contacts"""
		from .models import OrgAlertRecipient
		recipients = []
		for contact in contacts:
			recipients.append(OrgAlertRecipient(
				message=self,
				contact=contact,
				status='pending'
			))
		return OrgAlertRecipient.objects.bulk_create(recipients)

	def __str__(self):
		return f"Message to {self.organization.name} at {self.scheduled_time}"


class OrgAlertRecipient(models.Model):
	message = models.ForeignKey('OrgMessage', on_delete=models.CASCADE, related_name='recipients_status')
	contact = models.ForeignKey('Contact', on_delete=models.CASCADE)
	status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], default='pending')
	sent_at = models.DateTimeField(blank=True, null=True)
	error_message = models.TextField(blank=True, null=True)
	# Provider tracking and retry metadata
	provider_message_id = models.CharField(max_length=255, blank=True, null=True)
	provider_status = models.CharField(max_length=100, blank=True, null=True)
	retry_count = models.IntegerField(default=0)
	last_retry_at = models.DateTimeField(blank=True, null=True)
	# Soft delete for org admin visibility
	is_deleted = models.BooleanField(default=False)

	class Meta:
		indexes = [
			models.Index(fields=['status', 'sent_at']),
			models.Index(fields=['message', 'status']),
			models.Index(fields=['contact', 'status']),
			models.Index(fields=['is_deleted']),
			models.Index(fields=['message', 'is_deleted']),
			models.Index(fields=['contact', 'sent_at']),
			models.Index(fields=['status', 'retry_count']),
		]

	def mark_as_sent(self, provider_message_id=None):
		"""Mark recipient as sent with optional provider tracking"""
		from django.utils import timezone
		self.status = 'sent'
		self.sent_at = timezone.now()
		if provider_message_id:
			self.provider_message_id = provider_message_id
		self.save(update_fields=['status', 'sent_at', 'provider_message_id'])

	def mark_as_failed(self, error_message=None, provider_message_id=None):
		"""Mark recipient as failed with error details"""
		from django.utils import timezone
		self.status = 'failed'
		self.error_message = error_message or ''
		if provider_message_id:
			self.provider_message_id = provider_message_id
		self.retry_count += 1
		self.last_retry_at = timezone.now()
		self.save(update_fields=['status', 'error_message', 'provider_message_id', 'retry_count', 'last_retry_at'])

	def can_retry(self, max_retries=3):
		"""Check if this recipient can be retried"""
		return self.status in ['pending', 'failed'] and self.retry_count < max_retries

	def __str__(self):
		return f"{self.contact.name} - {self.status}"


class Organization(models.Model):
	TYPE_CHOICES = [
		("pharmacy", "Pharmacy"),
		("company", "Company"),
		("ngo", "NGO"),
		("other", "Other"),
	]
	name = models.CharField(max_length=255)
	org_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="company")
	slug = models.SlugField(max_length=100, unique=True)
	logo = models.ImageField(upload_to='org_logos/', blank=True, null=True)
	address = models.TextField(blank=True, null=True)
	phone_primary = models.CharField(max_length=20, blank=True, null=True)
	phone_secondary = models.CharField(max_length=20, blank=True, null=True)
	# ClickSend per-tenant credentials & sender id
	clicksend_username = models.CharField(max_length=100, blank=True, null=True)
	clicksend_api_key = models.CharField(max_length=100, blank=True, null=True)
	sender_id = models.CharField(max_length=50, blank=True, null=True)
	# Hubtel per-tenant credentials (optional)
	hubtel_api_url = models.CharField(max_length=255, blank=True, null=True)
	hubtel_client_id = models.CharField(max_length=255, blank=True, null=True)
	hubtel_client_secret = models.CharField(max_length=255, blank=True, null=True)
	hubtel_api_key = models.CharField(max_length=255, blank=True, null=True)
	hubtel_sender_id = models.CharField(max_length=50, blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	# administrative flags
	is_active = models.BooleanField(default=True)
	onboarded = models.BooleanField(default=False)
	# approval workflow
	APPROVAL_CHOICES = [
		('pending', 'Pending Approval'),
		('approved', 'Approved'),
		('rejected', 'Rejected'),
	]
	approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='pending')
	approved_at = models.DateTimeField(blank=True, null=True)
	approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_organizations')
	rejection_reason = models.TextField(blank=True, null=True)
	# billing
	balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
	# SMS usage tracking for pay-as-you-go billing
	total_sms_sent = models.PositiveIntegerField(default=0, help_text="Total SMS sent by organization")
	sms_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.25'), help_text="Cost per SMS in cedis")
	is_premium = models.BooleanField(default=False, help_text="Premium features enabled")

	class Meta:
		indexes = [
			models.Index(fields=['is_active', 'onboarded']),
			models.Index(fields=['slug']),
			models.Index(fields=['approval_status', 'created_at']),
		]

	def get_current_sms_rate(self):
		"""Calculate current SMS rate based on volume tiers"""
		# Volume-based pricing: higher volume = lower rate
		if self.total_sms_sent >= 10000:  # 10k+ SMS
			return Decimal('0.14')
		elif self.total_sms_sent >= 5000:  # 5k-10k SMS
			return Decimal('0.16')
		elif self.total_sms_sent >= 1000:  # 1k-5k SMS
			return Decimal('0.18')
		elif self.total_sms_sent >= 500:   # 500-1k SMS
			return Decimal('0.20')
		elif self.total_sms_sent >= 100:   # 100-500 SMS
			return Decimal('0.22')
		else:  # 0-100 SMS
			return Decimal('0.25')

	def update_sms_rate(self):
		"""Update the stored SMS rate based on current volume"""
		self.sms_rate = self.get_current_sms_rate()
		self.save(update_fields=['sms_rate'])

	def can_send_sms(self, count=1):
		"""Check if organization can afford to send specified number of SMS"""
		required_balance = self.get_current_sms_rate() * count
		return self.balance >= required_balance

	def deduct_sms_cost(self, count):
		"""Deduct SMS cost from balance and update usage stats"""
		cost = self.get_current_sms_rate() * count
		if self.balance >= cost:
			self.balance -= cost
			self.total_sms_sent += count
			self.save(update_fields=['balance', 'total_sms_sent'])
			return True, cost
		return False, Decimal('0.00')

	def get_contacts_count(self):
		"""Get total number of contacts"""
		return self.contacts.count()

	def get_templates_count(self):
		"""Get total number of SMS templates"""
		return self.orgsmstemplate_set.count()

	def get_messages_count(self):
		"""Get total number of messages sent"""
		return self.orgmessage_set.count()

	def get_delivery_stats(self):
		"""Get delivery statistics for the organization"""
		from django.db.models import Count, Q
		stats = OrgAlertRecipient.objects.filter(message__organization=self).aggregate(
			total=Count('id'),
			sent=Count('id', filter=Q(status='sent')),
			failed=Count('id', filter=Q(status='failed')),
			pending=Count('id', filter=Q(status='pending'))
		)
		total = stats['total']
		sent = stats['sent']
		delivery_rate = (sent / total * 100) if total > 0 else 0

		return {
			'total_recipients': total,
			'sent_recipients': sent,
			'failed_recipients': stats['failed'],
			'pending_recipients': stats['pending'],
			'delivery_rate': delivery_rate
		}

	def get_sms_stats_today(self):
		"""Get SMS statistics for today"""
		from django.utils import timezone
		from django.db.models import Count
		today = timezone.now().date()

		return self.orgalertrecipient_set.filter(
			sent_at__date=today,
			status='sent'
		).count()

	def get_sms_stats_week(self):
		"""Get SMS statistics for the past week"""
		from django.utils import timezone
		from django.db.models import Count
		week_ago = timezone.now() - timezone.timedelta(days=7)

		return self.orgalertrecipient_set.filter(
			sent_at__gte=week_ago,
			status='sent'
		).count()

	def get_sms_stats_month(self):
		"""Get SMS statistics for the past month"""
		from django.utils import timezone
		from django.db.models import Count
		month_ago = timezone.now() - timezone.timedelta(days=30)

		return self.orgalertrecipient_set.filter(
			sent_at__gte=month_ago,
			status='sent'
		).count()

	def is_low_balance(self):
		"""Check if organization has low balance (can't send 10 SMS)"""
		return self.balance < (self.get_current_sms_rate() * 10)

	def is_critical_balance(self):
		"""Check if organization has critical balance (< 5 GHS)"""
		return self.balance < Decimal('5.00')

	def __str__(self):
		return f"{self.name} ({self.org_type})"


class Contact(models.Model):
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='contacts')
	name = models.CharField(max_length=255)
	phone_number = models.CharField(max_length=20)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		indexes = [
			models.Index(fields=['organization', 'created_at']),
			models.Index(fields=['organization', 'phone_number']),
			models.Index(fields=['organization', 'name']),
		]

	def clean(self):
		from django.core.exceptions import ValidationError
		if not self.phone_number.startswith('+'):
			raise ValidationError({'phone_number': 'Phone number must include country code, e.g., +233501234567'})

	def save(self, *args, **kwargs):
		self.full_clean()
		super().save(*args, **kwargs)

	@classmethod
	def bulk_create_from_csv(cls, csv_file, organization):
		"""Bulk create contacts from CSV file"""
		import csv, io
		from .utils import normalize_phone_number

		decoded = csv_file.read().decode('utf-8', errors='ignore')
		reader = csv.DictReader(io.StringIO(decoded))

		contacts_to_create = []
		for row in reader:
			phone = (row.get('phone') or row.get('phone_number') or '').strip()
			name = (row.get('name') or row.get('contact_name') or '').strip()

			if phone:
				normalized_phone = normalize_phone_number(phone) or phone
				if normalized_phone:
					contacts_to_create.append(cls(
						organization=organization,
						name=name or normalized_phone,
						phone_number=normalized_phone
					))

		return cls.objects.bulk_create(contacts_to_create, ignore_conflicts=True)

	@classmethod
	def bulk_create_from_text(cls, text, organization):
		"""Bulk create contacts from pasted text"""
		import re
		from .utils import normalize_phone_number

		contacts_to_create = []
		# Extract phone numbers from text
		phones = re.findall(r'\+?\d{7,15}', text)

		for phone in phones:
			normalized_phone = normalize_phone_number(phone) or phone
			if normalized_phone:
				contacts_to_create.append(cls(
					organization=organization,
					name=normalized_phone,
					phone_number=normalized_phone
				))

		return cls.objects.bulk_create(contacts_to_create, ignore_conflicts=True)

	def get_display_name(self):
		"""Get display name for the contact"""
		return self.name if self.name else self.phone_number

	def __str__(self):
		return f"{self.name} ({self.phone_number})"


class ContactGroup(models.Model):
	"""Groups of contacts inside an Organization for easy targeting."""
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='groups')
	name = models.CharField(max_length=100)
	contacts = models.ManyToManyField(Contact, blank=True, related_name='groups')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.name} ({self.organization.name})"


class StatsViewer(models.Model):
	"""Optional mapping granting a user read-only 'stats' access to an Organization.

	This allows org admins to invite users who may only view dashboards and reports
	without being granted the ORG_ADMIN role across the app.
	"""
	user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='stats_views')
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='stats_viewers')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ('user', 'organization')

	def __str__(self):
		return f"{self.user.username} (stats) @ {self.organization.name}"


class SupportTicket(models.Model):
	"""Support tickets created by org admins to contact CedCast super-admins."""
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='support_tickets')
	created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
	subject = models.CharField(max_length=200)
	message = models.TextField()
	status = models.CharField(max_length=20, default='open')  # open, closed
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f"[{self.organization.slug}] {self.subject} ({self.status})"


class Payment(models.Model):
	"""Track balance additions via Paystack payments"""
	organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='payments')
	amount = models.DecimalField(max_digits=10, decimal_places=2)
	paystack_reference = models.CharField(max_length=100, unique=True)
	paystack_transaction_id = models.CharField(max_length=100, blank=True, null=True)
	status = models.CharField(max_length=20, choices=[
		('pending', 'Pending'),
		('success', 'Success'),
		('failed', 'Failed'),
		('cancelled', 'Cancelled'),
	], default='pending')
	processed_at = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']
		indexes = [
			models.Index(fields=['organization', 'status']),
			models.Index(fields=['paystack_reference']),
			models.Index(fields=['created_at']),
		]

	def __str__(self):
		return f"{self.organization.name} - ₵{self.amount} ({self.status})"


class Package(models.Model):
	"""SMS packages for organizations"""
	PACKAGE_TYPE_CHOICES = [
		('expiry', 'Expiry Package'),
		('non_expiry', 'Non-Expiry Package'),
	]
	name = models.CharField(max_length=100)
	description = models.TextField(blank=True, null=True)
	price = models.DecimalField(max_digits=10, decimal_places=2)
	sms_count = models.PositiveIntegerField(help_text="Number of SMS included in the package")
	expiry_days = models.PositiveIntegerField(default=0, help_text="Days until package expires (0 for non-expiry)")
	package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES)
	is_premium = models.BooleanField(default=False, help_text="Grants premium features")
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['price']

	def __str__(self):
		return f"{self.name} - {self.sms_count} SMS ({self.package_type})"


class EnrollmentRequest(models.Model):
	"""Model for public enrollment requests that need superadmin approval"""
	STATUS_CHOICES = [
		('pending', 'Pending Review'),
		('approved', 'Approved'),
		('rejected', 'Rejected'),
	]

	ORG_TYPE_CHOICES = [
		('company', 'Company'),
		('school', 'School'),
		('ngo', 'NGO'),
		('pharmacy', 'Pharmacy'),
		('restaurant', 'Restaurant'),
		('other', 'Other'),
	]

	# Organization details
	org_name = models.CharField(max_length=255)
	org_type = models.CharField(max_length=20, choices=ORG_TYPE_CHOICES, default='company')
	address = models.TextField(blank=True, null=True)

	# Contact person details
	contact_name = models.CharField(max_length=255)
	position = models.CharField(max_length=100, blank=True, null=True)
	email = models.EmailField()
	phone = models.CharField(max_length=20)

	# Additional information
	message = models.TextField(blank=True, null=True, help_text="Additional information from the requester")

	# Status and processing
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
	reviewed_at = models.DateTimeField(blank=True, null=True)
	reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests')
	review_notes = models.TextField(blank=True, null=True)

	# Timestamps
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']
		indexes = [
			models.Index(fields=['status', 'created_at']),
			models.Index(fields=['email']),
		]

	def __str__(self):
		return f"{self.org_name} - {self.contact_name} ({self.status})"
