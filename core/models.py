
from django.db import models
from django.contrib.auth.models import AbstractUser

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

	def __str__(self):
		return f"{self.name} ({self.organization.name})"

class School(models.Model):
	name = models.CharField(max_length=255)
	logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
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

	def __str__(self):
		return f"Message to {self.school.name} at {self.scheduled_time}"


class OrgMessage(models.Model):
	organization = models.ForeignKey('Organization', on_delete=models.CASCADE)
	content = models.TextField()
	scheduled_time = models.DateTimeField()
	sent = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)

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
	primary_color = models.CharField(max_length=7, default="#0d6efd")
	secondary_color = models.CharField(max_length=7, default="#6c757d")
	# ClickSend per-tenant credentials & sender id
	clicksend_username = models.CharField(max_length=100, blank=True, null=True)
	clicksend_api_key = models.CharField(max_length=100, blank=True, null=True)
	sender_id = models.CharField(max_length=20, blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.name} ({self.org_type})"


class Contact(models.Model):
	organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='contacts')
	name = models.CharField(max_length=255)
	phone_number = models.CharField(max_length=20)
	created_at = models.DateTimeField(auto_now_add=True)

	def clean(self):
		from django.core.exceptions import ValidationError
		if not self.phone_number.startswith('+'):
			raise ValidationError({'phone_number': 'Phone number must include country code, e.g., +233501234567'})

	def save(self, *args, **kwargs):
		self.full_clean()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.name} ({self.phone_number})"
