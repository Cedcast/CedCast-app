def home_view(request):
	from django.db.models import Sum, Count
	from django.db.models.functions import TruncMonth
	from .models import OrgMessage, OrgAlertRecipient

	# Get platform statistics
	total_orgs = Organization.objects.filter(is_active=True).count()
	total_sms_sent = OrgAlertRecipient.objects.filter(status='sent').count()

	# Get recent activity (last 30 days)
	thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
	recent_sms = OrgAlertRecipient.objects.filter(
		sent_at__gte=thirty_days_ago,
		status='sent'
	).count()

	# Get active organizations with recent activity
	active_orgs_recent = Organization.objects.filter(
		is_active=True,
		orgmessage__created_at__gte=thirty_days_ago
	).distinct().count()

	context = {
		'total_orgs': total_orgs,
		'total_sms_sent': total_sms_sent,
		'recent_sms': recent_sms,
		'active_orgs_recent': active_orgs_recent,
	}

	return render(request, "home.html", context)
from django.conf import settings
from core.hubtel_utils import send_sms
from django.utils.text import slugify
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from .models import User, School, Organization, Package, EnrollmentRequest
from django.http import JsonResponse, HttpResponse
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json
import os


def health(request):
	"""Simple health check endpoint for Render and load balancers."""
	return HttpResponse("OK", status=200)


def enrollment_request_view(request):
	"""Handle public enrollment requests from the homepage modal."""
	from .models import EnrollmentRequest
	from django.core.mail import send_mail
	from django.conf import settings

	if request.method == 'POST':
		try:
			enrollment_request = EnrollmentRequest.objects.create(
				org_name=request.POST.get('org_name'),
				org_type=request.POST.get('org_type', 'company'),
				address=request.POST.get('address'),
				contact_name=request.POST.get('contact_name'),
				position=request.POST.get('position'),
				email=request.POST.get('email'),
				phone=request.POST.get('phone'),
				message=request.POST.get('message'),
				status='pending',  # Require super admin review before approval
			)

			# Send notification email to superadmin (if email is configured)
			try:
				admin_email = getattr(settings, 'ADMIN_EMAIL', None)
				if admin_email:
					send_mail(
						subject=f'New Enrollment Request: {enrollment_request.org_name}',
						message=f"""
New enrollment request received and pending review:

Organization: {enrollment_request.org_name}
Type: {enrollment_request.org_type}
Contact: {enrollment_request.contact_name}
Position: {enrollment_request.position}
Email: {enrollment_request.email}
Phone: {enrollment_request.phone}
Address: {enrollment_request.address or 'Not provided'}

Message:
{enrollment_request.message or 'No additional message'}

Please review this request in the super admin dashboard and approve or reject as appropriate.
						""",
						from_email=settings.DEFAULT_FROM_EMAIL,
						recipient_list=[admin_email],
						fail_silently=True,
					)
			except Exception as e:
				# Log email error but don't fail the request
				import logging
				logger = logging.getLogger(__name__)
				logger.warning(f"Failed to send enrollment notification email: {e}")

			# Send SMS notification to superadmin (if phone is configured)
			try:
				admin_phone = getattr(settings, 'ADMIN_PHONE', None)
				if admin_phone:
					sms_message = f"New enrollment request: {enrollment_request.org_name} from {enrollment_request.contact_name}. Review in super admin dashboard."
					# Use None for tenant since this is a system notification
					send_sms(admin_phone, sms_message, None)
			except Exception as e:
				# Log SMS error but don't fail the request
				import logging
				logger = logging.getLogger(__name__)
				logger.warning(f"Failed to send enrollment notification SMS: {e}")

			return JsonResponse({
				'success': True,
				'message': 'Your enrollment request has been submitted successfully! Our team will review it and contact you within 24 hours.'
			})

		except Exception as e:
			return JsonResponse({
				'success': False,
				'message': 'There was an error submitting your request. Please try again or contact support.'
			}, status=400)

	return JsonResponse({
		'success': False,
		'message': 'Invalid request method.'
	}, status=405)





@login_required
def profile_view(request):
	user = request.user
	notice = None
	if request.method == 'POST':
		user.first_name = request.POST.get('first_name', user.first_name)
		user.last_name = request.POST.get('last_name', user.last_name)
		user.email = request.POST.get('email', user.email)
		user.save()
		notice = 'Profile updated successfully.'
	return render(request, 'profile.html', {'user': user, 'notice': notice})

@login_required
def billing_redirect(request):
	user = request.user
	if user.role == User.ORG_ADMIN and getattr(user, 'organization', None):
		return redirect('org_billing', org_slug=user.organization.slug)
	else:
		return redirect('dashboard')

@login_required
def send_sms_view(request, school_slug=None):
	user = request.user
	if user.role != User.SCHOOL_ADMIN:
		return redirect("dashboard")
	school = user.school
	# If a slug is provided in URL, enforce it matches the user's school
	if school_slug and school and school.slug != school_slug:
		return redirect("school_dashboard", school_slug=school.slug)
	message_sent = False
	error = None
	sent_class = None
	if request.method == "POST":
		sms_body = request.POST.get("sms_body")
		selected_class = request.POST.get("student_class")
		if sms_body:
			try:
				# Get parents whose wards are in the selected class
				from .models import Ward
				wards = Ward.objects.filter(school=school, student_class=selected_class)
				parents = set(ward.parent for ward in wards)
				for parent in parents:
					# try to capture provider message id when sending from the UI
					try:
						message_id = send_sms(parent.phone_number, sms_body, school)
						# best-effort: if there's an AlertRecipient for this message, save it
						from .models import AlertRecipient
						ar_qs = AlertRecipient.objects.filter(parent=parent, message__content=sms_body).order_by('-id')
						if ar_qs.exists():
							ar = ar_qs.first()
							if ar:
								ar.provider_message_id = message_id
								ar.save()
					except Exception:
						# ignore per-recipient failures in the UI loop
						pass
				message_sent = True
				sent_class = selected_class
			except Exception as e:
				error = str(e)
	return render(request, "send_sms.html", {"school": school, "message_sent": message_sent, "error": error, "sent_class": sent_class})
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import User, School

def login_view(request):
	if request.method == "POST":
		username = request.POST["username"]
		password = request.POST["password"]
		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)
			# Redirect by role
			if user.role == User.SUPER_ADMIN:  # type: ignore
				return redirect("dashboard")
			elif user.role == User.SCHOOL_ADMIN and user.school:  # type: ignore
				return redirect("school_dashboard", school_slug=user.school.slug)  # type: ignore
			elif user.role == User.ORG_ADMIN and getattr(user, 'organization', None):  # type: ignore
				return redirect("org_dashboard", org_slug=user.organization.slug)  # type: ignore
			return redirect("dashboard")
		else:
			return render(request, "login.html", {"error": "Invalid credentials"})
	return render(request, "login.html")


def _process_login(request, template_name, allowed_roles=None):
	"""Shared login handler that renders the given template name.

	allowed_roles: optional iterable of role constants allowed to authenticate
	via this page. If None, any authenticated user may login.
	"""
	# If the user is already authenticated, redirect them away if they
	# don't have an allowed role for this page.
	if request.user.is_authenticated:
		if allowed_roles is None or getattr(request.user, 'role', None) in (allowed_roles if isinstance(allowed_roles, (list, tuple, set)) else [allowed_roles]):
			# already logged in and allowed here — send to their dashboard
			if request.user.role == User.SUPER_ADMIN:
				return redirect("dashboard")
			if request.user.role == User.SCHOOL_ADMIN and getattr(request.user, 'school', None):
				return redirect("school_dashboard", school_slug=request.user.school.slug)
			if request.user.role == User.ORG_ADMIN and getattr(request.user, 'organization', None):
				return redirect("org_dashboard", org_slug=request.user.organization.slug)
			return redirect("dashboard")
		else:
			# already logged in but not allowed to use this page
			return redirect("dashboard")

	# recaptcha: read site/secret keys from settings
	recaptcha_site = getattr(settings, 'RECAPTCHA_SITE_KEY', None)
	recaptcha_secret = getattr(settings, 'RECAPTCHA_SECRET_KEY', None)

	if request.method == "POST":
		# If recaptcha is enabled, validate it first
		if recaptcha_secret:
			token = request.POST.get('g-recaptcha-response')
			if not token:
				return render(request, template_name, {"error": "Please complete the reCAPTCHA.", 'recaptcha_site_key': recaptcha_site})
			try:
				import requests
				resp = requests.post('https://www.google.com/recaptcha/api/siteverify', data={'secret': recaptcha_secret, 'response': token, 'remoteip': request.META.get('REMOTE_ADDR')}, timeout=5)
				data = resp.json()
				if not data.get('success'):
					return render(request, template_name, {"error": "reCAPTCHA validation failed.", 'recaptcha_site_key': recaptcha_site})
			except Exception:
				return render(request, template_name, {"error": "Could not validate reCAPTCHA.", 'recaptcha_site_key': recaptcha_site})
		username = request.POST.get("username")
		password = request.POST.get("password")
		user = authenticate(request, username=username, password=password)
		if user is not None:
			# If this page restricts which roles may login here, enforce it before logging in
			if allowed_roles is not None:
				allowed = allowed_roles if isinstance(allowed_roles, (list, tuple, set)) else [allowed_roles]
				if getattr(user, 'role', None) not in allowed:
					# don't log the user in here; show a helpful message
					return render(request, template_name, {"error": "Please use the Organization / School Admin login for your account.", 'recaptcha_site_key': recaptcha_site})

			# perform login and redirect by role
			login(request, user)
			if user.role == User.SUPER_ADMIN:  # type: ignore
				return redirect("dashboard")
			elif user.role == User.SCHOOL_ADMIN and getattr(user, 'school', None):  # type: ignore
				return redirect("school_dashboard", school_slug=user.school.slug)  # type: ignore
			elif user.role == User.ORG_ADMIN and getattr(user, 'organization', None):  # type: ignore
				return redirect("org_dashboard", org_slug=user.organization.slug)  # type: ignore
			return redirect("dashboard")
		else:
			return render(request, template_name, {"error": "Invalid credentials", 'recaptcha_site_key': recaptcha_site})
	return render(request, template_name, {'recaptcha_site_key': recaptcha_site})


def login_super_view(request):
	# Only SUPER_ADMIN may log in here
	return _process_login(request, "login_super.html", allowed_roles=[User.SUPER_ADMIN])


def login_org_view(request):
	# Allow both SCHOOL_ADMIN and ORG_ADMIN on this page
	return _process_login(request, "login_org.html", allowed_roles=[User.SCHOOL_ADMIN, User.ORG_ADMIN])


def login_redirect(request):
	# default /login/ redirects to organization/school admin login
	return redirect("login_org")

def logout_view(request):
	logout(request)
	return redirect("login")


# Temporary internal endpoint removed after creating the super admin in production.
# The creation was performed and verified; keep codebase clean for production.

@login_required
def dashboard(request, school_slug=None):
	user = request.user
	if user.role == User.SUPER_ADMIN:
		notice = None
		if request.method == "POST":
			entity_type = request.POST.get("entity_type", "school")
			name = request.POST.get("name")
			clicksend_username = request.POST.get("clicksend_username")
			clicksend_api_key = request.POST.get("clicksend_api_key")
			sender_id = request.POST.get("sender_id")
			logo_file = request.FILES.get("logo")
			primary_color = "#000000"
			secondary_color = "#FFFFFF"
			logo_path = None
			if logo_file:
				from django.core.files.storage import default_storage
				from django.core.files.base import ContentFile
				import os
				from colorthief import ColorThief
				# Save the uploaded logo temporarily
				temp_logo_path = default_storage.save(f"temp/{logo_file.name}", ContentFile(logo_file.read()))
				temp_logo_full_path = os.path.join(settings.MEDIA_ROOT, temp_logo_path)
				try:
					color_thief = ColorThief(temp_logo_full_path)
					dominant_color = color_thief.get_color(quality=1)
					palette = color_thief.get_palette(color_count=2)
					# Convert RGB to HEX
					def rgb_to_hex(rgb):
						return '#%02x%02x%02x' % rgb
					primary_color = rgb_to_hex(dominant_color)
					if palette and len(palette) > 1:
						secondary_color = rgb_to_hex(palette[1])
					else:
						secondary_color = rgb_to_hex(dominant_color)
				except Exception as e:
					pass  # fallback to defaults if extraction fails
			base_slug = slugify(name) if name else None
			unique_slug = base_slug
			counter = 2
			# Create tenant based on entity type
			if entity_type == "organization":
				from .models import Organization as OrgModel
				if logo_file:
					from django.core.files.storage import default_storage
					from django.core.files.base import ContentFile
					logo_path = default_storage.save(f"org_logos/{logo_file.name}", ContentFile(logo_file.read()))
				if base_slug:
					while OrgModel.objects.filter(slug=unique_slug).exists():
						unique_slug = f"{base_slug}-{counter}"
						counter += 1
				org = OrgModel.objects.create(
					name=name,
					org_type=request.POST.get("org_type", "company"),
					slug=unique_slug,
					primary_color=primary_color,
					secondary_color=secondary_color,
					clicksend_username=clicksend_username,
					clicksend_api_key=clicksend_api_key,
					sender_id=sender_id or None,
				)
				if logo_file and logo_path:
					org.logo.name = logo_path
					org.save()

					# Optionally create an organization admin account when provided
					admin_username = request.POST.get('admin_username')
					admin_email = request.POST.get('admin_email')
					if admin_username or admin_email:
						# pick a sensible username if only email provided
						base_username = admin_username or (admin_email.split('@')[0] if admin_email else f"{org.slug}_admin")
						username = base_username
						counter = 2
						from django.contrib.auth import get_user_model
						UserModel = get_user_model()
						while UserModel.objects.filter(username=username).exists():
							username = f"{base_username}{counter}"
							counter += 1
						# create user with a random temporary password and assign role/org
						import secrets
						temp_pw = secrets.token_urlsafe(10)
						user = UserModel.objects.create_user(username=username, email=admin_email or '', password=temp_pw)
						# set role and link to org (use model constant from our User model)
						setattr(user, 'role', User.ORG_ADMIN)
						setattr(user, 'organization', org)
						user.save()
						# If an email was provided, send password reset email so admin can set their password
						if admin_email:
							from django.contrib.auth.forms import PasswordResetForm
							reset_form = PasswordResetForm({'email': admin_email})
							if reset_form.is_valid():
								reset_form.save(request=request, use_https=request.is_secure(), email_template_name='registration/password_reset_email.html')
						notice = f"Organization '{org.name}' created. Admin account '{username}' created{' and password-reset email sent' if admin_email else ''}."
			else:
				from .models import School as SchoolModel
				if logo_file:
					from django.core.files.storage import default_storage
					from django.core.files.base import ContentFile
					logo_path = default_storage.save(f"school_logos/{logo_file.name}", ContentFile(logo_file.read()))
				if base_slug:
					while SchoolModel.objects.filter(slug=unique_slug).exists():
						unique_slug = f"{base_slug}-{counter}"
						counter += 1
				school = SchoolModel.objects.create(
					name=name,
					primary_color=primary_color,
					secondary_color=secondary_color,
					clicksend_username=clicksend_username,
					clicksend_api_key=clicksend_api_key,
					sender_id=sender_id or None,
					slug=unique_slug,
				)
				if logo_file and logo_path:
					school.logo.name = logo_path
					school.save()
		from .models import Message, AlertRecipient, Organization, OrgMessage, OrgAlertRecipient
		schools = School.objects.all()
		school_stats = []
		for school in schools:
			messages = Message.objects.filter(school=school)
			total_messages = messages.count()
			sent_messages = messages.filter(sent=True).count()
			recipients = AlertRecipient.objects.filter(message__school=school)
			total_recipients = recipients.count()
			sent_recipients = recipients.filter(status='sent').count()
			failed_recipients = recipients.filter(status='failed').count()
			delivery_rate = (sent_recipients / total_recipients * 100) if total_recipients else 0
			school_stats.append({
				'school': school,
				'total_messages': total_messages,
				'sent_messages': sent_messages,
				'total_recipients': total_recipients,
				'sent_recipients': sent_recipients,
				'failed_recipients': failed_recipients,
				'delivery_rate': delivery_rate,
			})
		orgs = Organization.objects.all()
		org_stats = []
		for org in orgs:
			messages = OrgMessage.objects.filter(organization=org)
			total_messages = messages.count()
			sent_messages = messages.filter(sent=True).count()
			recipients = OrgAlertRecipient.objects.filter(message__organization=org)
			total_recipients = recipients.count()
			sent_recipients = recipients.filter(status='sent').count()
			failed_recipients = recipients.filter(status='failed').count()
			delivery_rate = (sent_recipients / total_recipients * 100) if total_recipients else 0
			# decrypt sender id for display (secrets are stored encrypted)
			from .utils.crypto_utils import decrypt_value
			sender_id = getattr(org, 'sender_id', None)
			sender_display = decrypt_value(sender_id) if sender_id else None
			org_stats.append({
				'organization': org,
				'total_messages': total_messages,
				'sent_messages': sent_messages,
				'total_recipients': total_recipients,
				'sent_recipients': sent_recipients,
				'failed_recipients': failed_recipients,
				'delivery_rate': delivery_rate,
				'sender_id_display': sender_display,
			})
		# Overall message totals for the chart
		from .models import Message as SchoolMessage, OrgMessage as OrganizationMessage
		total_msgs = SchoolMessage.objects.count() + OrganizationMessage.objects.count()
		total_sent = SchoolMessage.objects.filter(sent=True).count() + OrganizationMessage.objects.filter(sent=True).count()
		# Build 7-day trends (oldest -> newest)
		from django.utils import timezone
		import datetime
		from django.db.models.functions import TruncDate
		from django.db.models import Count
		trend_days = 7
		now = timezone.now()
		start_date = (now - datetime.timedelta(days=trend_days - 1)).date()
		# Aggregate sent counts by sent_at date for school and org recipients
		from .models import AlertRecipient as SchoolAlertRecipient, OrgAlertRecipient as OrganizationAlertRecipient
		sent_school_qs = SchoolAlertRecipient.objects.filter(status='sent', sent_at__date__gte=start_date).annotate(day=TruncDate('sent_at')).values('day').annotate(count=Count('id'))
		sent_org_qs = OrganizationAlertRecipient.objects.filter(status='sent', sent_at__date__gte=start_date).annotate(day=TruncDate('sent_at')).values('day').annotate(count=Count('id'))
		# Aggregate totals by message created date (for delivery denominator)
		total_school_qs = SchoolAlertRecipient.objects.filter(message__created_at__date__gte=start_date).annotate(day=TruncDate('message__created_at')).values('day').annotate(total=Count('id'))
		total_org_qs = OrganizationAlertRecipient.objects.filter(message__created_at__date__gte=start_date).annotate(day=TruncDate('message__created_at')).values('day').annotate(total=Count('id'))
		# Aggregate org creations
		orgs_qs = Organization.objects.filter(created_at__date__gte=start_date).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id'))
		# build dicts keyed by date for quick lookup
		sent_by_date = {}
		for r in sent_school_qs:
			sent_by_date[r['day']] = sent_by_date.get(r['day'], 0) + r['count']
		for r in sent_org_qs:
			sent_by_date[r['day']] = sent_by_date.get(r['day'], 0) + r['count']
		total_by_date = {}
		for r in total_school_qs:
			total_by_date[r['day']] = total_by_date.get(r['day'], 0) + r['total']
		for r in total_org_qs:
			total_by_date[r['day']] = total_by_date.get(r['day'], 0) + r['total']
		orgs_by_date = { r['day']: r['count'] for r in orgs_qs }
		# Build arrays oldest->newest
		messages_trend = []
		orgs_trend = []
		delivery_trend = []
		for i in range(trend_days - 1, -1, -1):
			d = (now - datetime.timedelta(days=i)).date()
			messages_trend.append(sent_by_date.get(d, 0))
			orgs_trend.append(orgs_by_date.get(d, 0))
			total = total_by_date.get(d, 0)
			sent = sent_by_date.get(d, 0)
			delivery_trend.append(int((sent / total * 100)) if total else 0)

		# Billing analytics
		from .models import Payment
		from django.db.models import Sum, Count, Avg
		from decimal import Decimal

		# Payment statistics
		total_payments = Payment.objects.filter(status='success').count()
		total_revenue = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
		recent_payments = Payment.objects.filter(status='success', created_at__date__gte=start_date).count()

		# Organization balance statistics
		orgs_with_balance = Organization.objects.filter(balance__gt=Decimal('0')).count()
		total_org_balance = Organization.objects.aggregate(total=Sum('balance'))['total'] or Decimal('0')
		avg_org_balance = total_org_balance / orgs_with_balance if orgs_with_balance > 0 else Decimal('0')

		# Premium organizations statistics
		premium_orgs = Organization.objects.filter(is_premium=True).count()
		total_orgs = Organization.objects.count()
		premium_percentage = (premium_orgs / total_orgs * 100) if total_orgs > 0 else 0

		# SMS usage statistics for pay-as-you-go
		total_sms_sent_all = Organization.objects.aggregate(total=Sum('total_sms_sent'))['total'] or 0
		total_balance_all = Organization.objects.aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
		avg_sms_rate = Organization.objects.aggregate(avg=Avg('sms_rate'))['avg'] or Decimal('0.25')

		# Recent payments trend (7 days)
		payments_trend = []
		for i in range(trend_days - 1, -1, -1):
			d = (now - datetime.timedelta(days=i)).date()
			day_payments = Payment.objects.filter(status='success', created_at__date=d).count()
			payments_trend.append(day_payments)

		# Recent payment transactions (last 10 successful payments)
		recent_payment_transactions = Payment.objects.filter(status='success').select_related('organization').order_by('-created_at')[:10]

		# Top paying organizations
		top_orgs = Organization.objects.filter(balance__gt=Decimal('0')).order_by('-balance')[:5]
		top_payers = []
		for org in top_orgs:
			total_paid = Payment.objects.filter(organization=org, status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
			top_payers.append({
				'organization': org,
				'balance': org.balance,
				'total_paid': total_paid,
			})

		# Pending organization approvals
		pending_approvals = Organization.objects.filter(approval_status='pending').order_by('-created_at')

		# Approved enrollment requests that need manual account creation
		approved_enrollment_requests = EnrollmentRequest.objects.filter(status='approved').order_by('-reviewed_at')[:10]  # Show latest 10

		# Pending enrollment requests that need review
		pending_enrollment_requests = EnrollmentRequest.objects.filter(status='pending').order_by('-created_at')[:10]  # Show latest 10

		context = {"schools": schools, "school_stats": school_stats, "org_stats": org_stats, "notice": notice,
			"total_messages": total_msgs, "total_sent": total_sent,
			"messages_trend": messages_trend, "orgs_trend": orgs_trend, "delivery_trend": delivery_trend,
			"hubtel_dry_run": getattr(settings, 'HUBTEL_DRY_RUN', False),
			"clicksend_dry_run": getattr(settings, 'CLICKSEND_DRY_RUN', False),
			# Billing analytics
			"total_payments": total_payments,
			"total_revenue": total_revenue,
			"recent_payments": recent_payments,
			"orgs_with_balance": orgs_with_balance,
			"total_org_balance": total_org_balance,
			"avg_org_balance": avg_org_balance,
			"payments_trend": payments_trend,
			"top_payers": top_payers,
			# Premium analytics
			"premium_orgs": premium_orgs,
			"total_orgs": total_orgs,
			"premium_percentage": premium_percentage,
			# Pay-as-you-go analytics
			"total_sms_sent_all": total_sms_sent_all,
			"total_balance_all": total_balance_all,
			"avg_sms_rate": avg_sms_rate,
			# Pending approvals
			"pending_approvals": pending_approvals,
			# Enrollment requests
			"approved_enrollment_requests": approved_enrollment_requests,
			"pending_enrollment_requests": pending_enrollment_requests,
			# Recent payment transactions
			"recent_payment_transactions": recent_payment_transactions,
		}
		return render(request, "super_admin_dashboard.html", context)



	elif user.role == User.SCHOOL_ADMIN:
		school = user.school
		if school_slug and school and school.slug != school_slug:
			return redirect("school_dashboard", school_slug=school.slug)
		if request.method == "POST":
			parent_name = request.POST.get("parent_name")
			parent_phone = request.POST.get("parent_phone")
			ward_name = request.POST.get("ward_name")
			sms_body = request.POST.get("sms_body")
			scheduled_time = request.POST.get("scheduled_time")
			recipients_str = request.POST.get("recipients")
			primary_color = request.POST.get("primary_color")
			secondary_color = request.POST.get("secondary_color")
			logo_file = request.FILES.get("logo")
			from .models import Parent, Ward, Message, AlertRecipient
			updated = False
			# Branding update
			if primary_color or secondary_color or logo_file:
				if primary_color:
					school.primary_color = primary_color
					updated = True
				if secondary_color:
					school.secondary_color = secondary_color
					updated = True
				if logo_file:
					school.logo = logo_file
					updated = True
				if updated:
					school.save()
			# Add parent/ward
			elif parent_name and parent_phone and ward_name:
				parent = Parent.objects.create(school=school, name=parent_name, phone_number=parent_phone)
				Ward.objects.create(school=school, parent=parent, name=ward_name)
			# Schedule SMS
			elif sms_body and scheduled_time:
				import datetime
				from django.utils import timezone
				scheduled_dt = timezone.make_aware(datetime.datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M"))
				message = Message.objects.create(
					school=school,
					content=sms_body,
					scheduled_time=scheduled_dt,
					sent=False,
					created_by=request.user
				)
				if recipients_str:
					phone_numbers = [num.strip() for num in recipients_str.split(",") if num.strip()]
					parents = Parent.objects.filter(school=school, phone_number__in=phone_numbers)
				else:
					parents = Parent.objects.filter(school=school)
				for parent in parents:
					AlertRecipient.objects.create(message=message, parent=parent, status='pending')
		from .models import Message
		messages = Message.objects.filter(school=school).order_by('-scheduled_time')
		return render(request, "school_admin_dashboard.html", {
			"school": school,
			"primary_color": school.primary_color,
			"secondary_color": school.secondary_color,
			"messages": messages
		})
	else:
		# For organization admins, redirect to their dashboard
		if user.role == User.ORG_ADMIN and getattr(user, 'organization', None):
			return redirect("org_dashboard", org_slug=user.organization.slug)
		return redirect("login")


@login_required
@user_passes_test(lambda u: u.role == User.SUPER_ADMIN)  # type: ignore
def approve_org_view(request, org_id):
	"""Approve a pending organization"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'error': 'Method not allowed'})
	
	try:
		organization = Organization.objects.get(id=org_id, approval_status='pending')
		organization.approval_status = 'approved'
		organization.approved_at = timezone.now()
		organization.approved_by = request.user
		organization.is_active = True
		# Don't mark as onboarded yet - they need to complete the wizard
		organization.save()
		
		# Send approval email to organization admin
		try:
			admin_user = User.objects.filter(organization=organization, role=User.ORG_ADMIN).first()
			if admin_user and admin_user.email:
				from django.core.mail import send_mail
				from django.template.loader import render_to_string
				from django.conf import settings
				
				subject = f"Welcome to CedCast! Your account has been approved"
				context = {
					'admin_name': admin_user.get_full_name() or admin_user.username,
					'organization': organization,
					'admin_username': admin_user.username,
					'temp_password': 'Please use the password reset link sent separately',
					'protocol': 'https',  # Assume production uses HTTPS
					'domain': getattr(settings, 'SITE_DOMAIN', 'cedcast.com'),
					'site_name': 'CedCast',
				}
				message = render_to_string('emails/organization_approved.html', context)
				send_mail(
					subject,
					message,
					settings.DEFAULT_FROM_EMAIL,
					[admin_user.email],
					fail_silently=True
				)
		except Exception as e:
			# Log the error but don't fail the approval
			import logging
			logger = logging.getLogger(__name__)
			logger.error(f"Failed to send approval email: {e}")
		
		return JsonResponse({'success': True})
	except Organization.DoesNotExist:
		return JsonResponse({'success': False, 'error': 'Organization not found or not pending'})
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(lambda u: u.role == User.SUPER_ADMIN)  # type: ignore
def reject_org_view(request, org_id):
	"""Reject a pending organization"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'error': 'Method not allowed'})
	
	try:
		reason = request.POST.get('reason', '').strip()
		if not reason:
			return JsonResponse({'success': False, 'error': 'Rejection reason is required'})
		
		organization = Organization.objects.get(id=org_id, approval_status='pending')
		organization.approval_status = 'rejected'
		organization.rejection_reason = reason
		organization.approved_at = timezone.now()
		organization.approved_by = request.user
		organization.save()
		
		# Send rejection email to organization admin
		try:
			admin_user = User.objects.filter(organization=organization, role=User.ORG_ADMIN).first()
			if admin_user and admin_user.email:
				from django.core.mail import send_mail
				from django.template.loader import render_to_string
				from django.conf import settings
				
				subject = f"CedCast Account Application Update"
				context = {
					'contact_name': admin_user.get_full_name() or admin_user.username,
					'org_name': organization.name,
					'rejection_reason': reason,
					'protocol': 'https',  # Assume production uses HTTPS
					'domain': getattr(settings, 'SITE_DOMAIN', 'cedcast.com'),
					'site_name': 'CedCast',
				}
				message = render_to_string('emails/organization_rejected.html', context)
				send_mail(
					subject,
					message,
					settings.DEFAULT_FROM_EMAIL,
					[admin_user.email],
					fail_silently=True
				)
		except Exception as e:
			# Log the error but don't fail the rejection
			import logging
			logger = logging.getLogger(__name__)
			logger.error(f"Failed to send rejection email: {e}")
		
		return JsonResponse({'success': True})
	except Organization.DoesNotExist:
		return JsonResponse({'success': False, 'error': 'Organization not found or not pending'})
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)})





@login_required
@user_passes_test(lambda u: u.role == User.SUPER_ADMIN)  # type: ignore
def approve_enrollment_request(request, request_id):
	"""Approve an enrollment request - mark as approved for manual processing"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'error': 'Method not allowed'})
	
	try:
		from .models import EnrollmentRequest
		enrollment_request = EnrollmentRequest.objects.get(id=request_id, status='pending')
		
		# Just mark as approved - super admin will manually create the organization
		enrollment_request.status = 'approved'
		enrollment_request.reviewed_at = timezone.now()
		enrollment_request.reviewed_by = request.user
		enrollment_request.save()
		
		# Send approval email to inform them their request was approved
		try:
			from django.core.mail import send_mail
			from django.template.loader import render_to_string
			from django.conf import settings
			
			subject = f"CedCast Enrollment Request Approved - {enrollment_request.org_name}"
			context = {
				'contact_name': enrollment_request.contact_name,
				'organization_name': enrollment_request.org_name,
				'protocol': 'https',
				'domain': getattr(settings, 'SITE_DOMAIN', 'cedcast.com'),
				'site_name': 'CedCast',
			}
			message = render_to_string('emails/enrollment_approved.html', context)
			send_mail(
				subject,
				message,
				settings.DEFAULT_FROM_EMAIL,
				[enrollment_request.email],
				fail_silently=True
			)
		except Exception as e:
			import logging
			logger = logging.getLogger(__name__)
			logger.error(f"Failed to send enrollment approval email: {e}")
		
		return JsonResponse({'success': True})
	except EnrollmentRequest.DoesNotExist:
		return JsonResponse({'success': False, 'error': 'Enrollment request not found or not pending'})
	except Exception as e:
		import logging
		logger = logging.getLogger(__name__)
		logger.error(f"Error approving enrollment request: {e}")
		return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(lambda u: u.role == User.SUPER_ADMIN)  # type: ignore
def reject_enrollment_request(request, request_id):
	"""Reject an enrollment request"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'error': 'Method not allowed'})
	
	try:
		from .models import EnrollmentRequest
		reason = request.POST.get('reason', '').strip()
		if not reason:
			return JsonResponse({'success': False, 'error': 'Rejection reason is required'})
		
		enrollment_request = EnrollmentRequest.objects.get(id=request_id, status__in=['pending', 'approved'])
		enrollment_request.status = 'rejected'
		enrollment_request.review_notes = reason
		enrollment_request.reviewed_at = timezone.now()
		enrollment_request.reviewed_by = request.user
		enrollment_request.save()
		
		# Send rejection email
		try:
			from django.core.mail import send_mail
			from django.template.loader import render_to_string
			from django.conf import settings
			
			subject = f"CedCast Enrollment Request Update"
			context = {
				'contact_name': enrollment_request.contact_name,
				'org_name': enrollment_request.org_name,
				'rejection_reason': reason,
				'protocol': 'https',
				'domain': getattr(settings, 'SITE_DOMAIN', 'cedcast.com'),
				'site_name': 'CedCast',
			}
			message = render_to_string('emails/enrollment_rejected.html', context)
			send_mail(
				subject,
				message,
				settings.DEFAULT_FROM_EMAIL,
				[enrollment_request.email],
				fail_silently=True
			)
		except Exception as e:
			import logging
			logger = logging.getLogger(__name__)
			logger.error(f"Failed to send enrollment rejection email: {e}")
		
		return JsonResponse({'success': True})
	except EnrollmentRequest.DoesNotExist:
		return JsonResponse({'success': False, 'error': 'Enrollment request not found or not pending'})
	except Exception as e:
		import logging
		logger = logging.getLogger(__name__)
		logger.error(f"Error rejecting enrollment request: {e}")
		return JsonResponse({'success': False, 'error': str(e)})




@login_required
def system_logs_view(request):
    # Super Admin only
    if not request.user.role == User.SUPER_ADMIN:
        return redirect('dashboard')
    # Use Django admin LogEntry to show recent admin actions
    from django.contrib.admin.models import LogEntry
    logs = LogEntry.objects.all().order_by('-action_time')[:200]
    return render(request, 'system_logs.html', {'logs': logs})


@login_required
@user_passes_test(lambda u: u.role == User.SUPER_ADMIN)
def audit_message_logs_view(request):
    """Comprehensive audit view of all organization message logs including deleted ones"""
    from .models import OrgAlertRecipient
    
    # filters
    status = request.GET.get('status')
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    org_slug = request.GET.get('org')
    show_deleted = request.GET.get('show_deleted', 'false') == 'true'
    
    logs = OrgAlertRecipient.objects.select_related('message__organization', 'contact').all()
    
    # Always show deleted logs for audit purposes
    if not show_deleted:
        logs = logs.filter(is_deleted=False)
    
    if status:
        logs = logs.filter(status=status)
    if org_slug:
        logs = logs.filter(message__organization__slug=org_slug)
        
    # Parse date filter inputs (expected YYYY-MM-DD). Use sent_at__date to avoid timezone-aware/datetime issues.
    import datetime as _dt
    if date_from:
        try:
            dfrom = _dt.date.fromisoformat(date_from)
            logs = logs.filter(sent_at__date__gte=dfrom)
        except Exception:
            # ignore bad input
            date_from = None
    if date_to:
        try:
            dto = _dt.date.fromisoformat(date_to)
            logs = logs.filter(sent_at__date__lte=dto)
        except Exception:
            date_to = None
    
    logs = logs.order_by('-sent_at')
    
    # Get organizations for filter dropdown
    organizations = Organization.objects.filter(is_active=True).order_by('name')
    
    context = {
        'logs': logs,
        'status': status,
        'from': date_from,
        'to': date_to,
        'org_slug': org_slug,
        'organizations': organizations,
        'show_deleted': show_deleted,
    }
    
    return render(request, 'audit_message_logs.html', context)


@login_required
def global_templates_view(request):
    if not request.user.role == User.SUPER_ADMIN:
        return redirect('dashboard')
    from .models import OrgSMSTemplate
    templates = OrgSMSTemplate.objects.select_related('organization').all().order_by('-created_at')
    return render(request, 'global_templates.html', {'templates': templates})


@login_required
def create_global_template_view(request):
	if not request.user.role == User.SUPER_ADMIN:
		return redirect('dashboard')
	from .models import OrgSMSTemplate, Organization
	notice = None
	# Ensure generated_credentials is always defined (avoid UnboundLocalError on GET)
	generated_credentials = None
	orgs = Organization.objects.all().order_by('name')
	# Support prefilling when copying an existing template via ?copy_from=<id>
	copy_from = request.GET.get('copy_from')
	prefill = {}
	if copy_from:
		try:
			src = OrgSMSTemplate.objects.get(id=copy_from)
			prefill['name'] = f"Copy of {src.name}"
			prefill['content'] = src.content
			prefill['organization'] = src.organization.id
		except OrgSMSTemplate.DoesNotExist:
			pass
	if request.method == 'POST':
		name = request.POST.get('name')
		org_id = request.POST.get('organization')
		content = request.POST.get('content')
		try:
			org = Organization.objects.get(id=org_id)
			tmpl = OrgSMSTemplate.objects.create(organization=org, name=name, content=content)
			notice = 'Template created.'
			# Audit
			try:
				from django.contrib.admin.models import LogEntry
				from django.contrib.contenttypes.models import ContentType
				ct = ContentType.objects.get_for_model(OrgSMSTemplate)
				LogEntry.objects.log_action(
					user_id=request.user.id,
					content_type_id=ct.id,
					object_id=getattr(tmpl, 'id', None),
					object_repr=str(tmpl),
					action_flag=1,
					change_message='Created global template',
				)
			except Exception:
				pass
			return redirect('global_templates')
		except Organization.DoesNotExist:
			notice = 'Organization not found.'
	context = {'orgs': orgs, 'notice': notice, 'action': 'create', 'prefill': prefill}
	return render(request, 'global_template_form.html', context)


@login_required
def edit_global_template_view(request, template_id):
	if not request.user.role == User.SUPER_ADMIN:
		return redirect('dashboard')
	from .models import OrgSMSTemplate, Organization
	try:
		tmpl = OrgSMSTemplate.objects.get(id=template_id)
	except OrgSMSTemplate.DoesNotExist:
		return redirect('global_templates')
	orgs = Organization.objects.all().order_by('name')
	notice = None
	generated_credentials = None
	if request.method == 'POST':
		tmpl.name = request.POST.get('name')
		org_id = request.POST.get('organization')
		try:
			tmpl.organization = Organization.objects.get(id=org_id)
		except Organization.DoesNotExist:
			notice = 'Organization not found.'
		tmpl.content = request.POST.get('content')
		tmpl.save()
		notice = 'Template updated.'
		try:
			from django.contrib.admin.models import LogEntry
			from django.contrib.contenttypes.models import ContentType
			ct = ContentType.objects.get_for_model(OrgSMSTemplate)
			LogEntry.objects.log_action(
				user_id=request.user.id,
				content_type_id=ct.id,
					object_id=getattr(tmpl, 'id', None),
				object_repr=str(tmpl),
				action_flag=2,
				change_message='Updated global template',
			)
		except Exception:
			pass
		return redirect('global_templates')

	return render(request, 'global_template_form.html', {'template': tmpl, 'orgs': orgs, 'action': 'edit'})


@login_required
def onboarding_view(request):
	# Super-admin only
	if not request.user.role == User.SUPER_ADMIN:
		return redirect('dashboard')

	from .models import Organization
	notice = None

	if request.method == 'POST':
		slug = request.POST.get('slug')
		sender_id = request.POST.get('sender_id')
		action = request.POST.get('action')
		try:
			org = Organization.objects.get(slug=slug)
			if action == 'configure':
				org.sender_id = sender_id or org.sender_id
				org.onboarded = True
				org.save()
				notice = f"Configured {org.name}"
				# Audit/log this change using Django admin LogEntry for traceability
				try:
					from django.contrib.admin.models import LogEntry
					from django.contrib.contenttypes.models import ContentType
					ct = ContentType.objects.get_for_model(Organization)
					LogEntry.objects.log_action(
						user_id=request.user.id,
						content_type_id=ct.id,
						object_id=getattr(org, 'id', None),
						object_repr=str(org),
						action_flag=2,  # change
						change_message=f"Configured sender_id={org.sender_id}",
					)
				except Exception:
					# don't break the user action if logging fails
					pass
			elif action == 'suspend':
				org.is_active = False
				org.save()
				notice = f"Suspended {org.name}"
				try:
					from django.contrib.admin.models import LogEntry
					from django.contrib.contenttypes.models import ContentType
					ct = ContentType.objects.get_for_model(Organization)
					LogEntry.objects.log_action(
						user_id=request.user.id,
						content_type_id=ct.id,
						object_id=getattr(org, 'id', None),
						object_repr=str(org),
						action_flag=2,
						change_message="Suspended organization via onboarding UI",
					)
				except Exception:
					pass
			elif action == 'activate':
				org.is_active = True
				org.save()
				notice = f"Activated {org.name}"
				try:
					from django.contrib.admin.models import LogEntry
					from django.contrib.contenttypes.models import ContentType
					ct = ContentType.objects.get_for_model(Organization)
					LogEntry.objects.log_action(
						user_id=request.user.id,
						content_type_id=ct.id,
						object_id=getattr(org, 'id', None),
						object_repr=str(org),
						action_flag=2,
						change_message="Activated organization via onboarding UI",
					)
				except Exception:
					pass
		except Organization.DoesNotExist:
			notice = 'Organization not found.'

	orgs = Organization.objects.all().order_by('-created_at')
	return render(request, 'onboarding.html', {'orgs': orgs, 'notice': notice})


@login_required
def super_edit_org_view(request, org_slug=None):
	# Only super admin may edit org credentials
	if request.user.role != User.SUPER_ADMIN:
		return redirect('dashboard')

	from .models import Organization
	try:
		org = Organization.objects.get(slug=org_slug)
	except Organization.DoesNotExist:
		return redirect('onboarding')

	from .utils.crypto_utils import encrypt_value
	notice = None
	if request.method == 'POST':
		# update credential fields (encrypt secrets before saving)
		org.hubtel_api_url = request.POST.get('hubtel_api_url') or org.hubtel_api_url
		org.hubtel_client_id = request.POST.get('hubtel_client_id') or org.hubtel_client_id
		posted = request.POST.get('hubtel_client_secret')
		if posted:
			org.hubtel_client_secret = encrypt_value(posted)
		# if empty, leave existing value unchanged
		posted_key = request.POST.get('hubtel_api_key')
		if posted_key:
			org.hubtel_api_key = encrypt_value(posted_key)
		# Hubtel sender id (separate from generic sender_id)
		posted_hubtel_sender = request.POST.get('hubtel_sender_id')
		if posted_hubtel_sender:
			org.hubtel_sender_id = encrypt_value(posted_hubtel_sender)

		posted_clicksend_key = request.POST.get('clicksend_api_key')
		if posted_clicksend_key:
			org.clicksend_api_key = encrypt_value(posted_clicksend_key)
		# non-secret fields
		org.clicksend_username = request.POST.get('clicksend_username') or org.clicksend_username
		posted_sender = request.POST.get('sender_id')
		if posted_sender:
			org.sender_id = encrypt_value(posted_sender)
		# flags
		org.onboarded = bool(request.POST.get('onboarded'))
		# is_active checkbox is present when checked; default leave unchanged
		if request.POST.get('is_active') is not None:
			org.is_active = bool(request.POST.get('is_active'))
		org.save()
		notice = 'Organization credentials updated.'
		# Audit
		try:
			from django.contrib.admin.models import LogEntry
			from django.contrib.contenttypes.models import ContentType
			ct = ContentType.objects.get_for_model(Organization)
			LogEntry.objects.log_action(
				user_id=request.user.id,
				content_type_id=ct.id,
				object_id=getattr(org, 'id', None),
				object_repr=str(org),
				action_flag=2,
				change_message='Updated organization credentials via super admin UI',
			)
		except Exception:
			pass
		# provide flags for the template to show masked indicators
		context = {'org': org, 'notice': notice,
				   'hubtel_secret_present': bool(org.hubtel_client_secret),
				   'clicksend_key_present': bool(org.clicksend_api_key),
				   'sender_present': bool(org.sender_id)}
		return render(request, 'super_org_edit.html', context)

	context = {'org': org, 'notice': notice,
			   'hubtel_secret_present': bool(org.hubtel_client_secret),
			   'clicksend_key_present': bool(org.clicksend_api_key),
			   'sender_present': bool(org.sender_id)}
	return render(request, 'super_org_edit.html', context)

@login_required
def org_dashboard(request, org_slug=None):
	user = request.user
	# Allow ORG_ADMIN or stats-viewer users to view dashboard
	from .models import StatsViewer
	is_stats_viewer = False
	if getattr(user, 'is_authenticated', False):
		try:
			is_stats_viewer = StatsViewer.objects.filter(user=user, organization=getattr(user, 'organization', None)).exists()
		except Exception:
			is_stats_viewer = False
	if not (user.role == User.ORG_ADMIN or is_stats_viewer) or not getattr(user, 'organization', None):
		return redirect("dashboard")
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect("org_dashboard", org_slug=organization.slug)

	message_sent = False
	error = None
	if request.method == "POST":
		if not organization.is_active:
			error = 'Your organization account is suspended. Please contact support.'
		else:
			from .models import Contact, OrgMessage, OrgAlertRecipient
			# Add contact
			contact_name = request.POST.get("contact_name")
			raw_phone = request.POST.get("contact_phone")
			sms_body = request.POST.get("sms_body")
			scheduled_time = request.POST.get("scheduled_time")
			recipients_str = request.POST.get("recipients")

			if contact_name and raw_phone:
				from .utils import normalize_phone_number
				phone_number = normalize_phone_number(raw_phone)
				Contact.objects.create(organization=organization, name=contact_name, phone_number=phone_number)
			elif sms_body and scheduled_time:
				import datetime
				from django.utils import timezone
				scheduled_dt = timezone.make_aware(datetime.datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M"))
				msg = OrgMessage.objects.create(
					organization=organization,
					content=sms_body,
					scheduled_time=scheduled_dt,
					sent=False,
					created_by=request.user,
				)
				if recipients_str:
					phone_numbers = [num.strip() for num in recipients_str.split(",") if num.strip()]
					contacts = Contact.objects.filter(organization=organization, phone_number__in=phone_numbers)
				else:
					contacts = Contact.objects.filter(organization=organization)
				for c in contacts:
					OrgAlertRecipient.objects.create(message=msg, contact=c, status='pending')

	from .models import OrgMessage
	from django.core.cache import cache
	cache_key = f"org_dashboard_metrics_{organization.id}"

	# Try to get cached metrics, but handle cache failures gracefully
	try:
		cached_metrics = cache.get(cache_key)
	except Exception:
		# If caching fails for any reason, just proceed without cache
		cached_metrics = None

	if cached_metrics:
		messages = cached_metrics['messages']
		contacts_count = cached_metrics['contacts_count']
		templates_count = cached_metrics['templates_count']
		msgs_sent_today = cached_metrics['msgs_sent_today']
		msgs_sent_week = cached_metrics['msgs_sent_week']
		msgs_sent_month = cached_metrics['msgs_sent_month']
		total_recipients = cached_metrics['total_recipients']
		sent_recipients = cached_metrics['sent_recipients']
		delivery_rate = cached_metrics['delivery_rate']
		msgs_sent_trend = cached_metrics['msgs_sent_trend']
		contacts_trend = cached_metrics['contacts_trend']
		templates_trend = cached_metrics['templates_trend']
		delivery_trend = cached_metrics['delivery_trend']
	else:
		messages = OrgMessage.objects.filter(organization=organization).select_related('created_by').order_by('-scheduled_time')[:getattr(settings, 'DEFAULT_DASHBOARD_MESSAGES_LIMIT', 10)]  # Limit to recent messages
		# compute org-level metrics for dashboard
		from django.utils import timezone
		import datetime
		from .models import OrgAlertRecipient, OrgSMSTemplate, Contact

		now = timezone.now()
		start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
		start_week = now - datetime.timedelta(days=7)
		start_month = now - datetime.timedelta(days=30)

		# Use aggregate queries for better performance
		from django.db.models import Count, Q
		contacts_count = Contact.objects.filter(organization=organization).count()
		templates_count = OrgSMSTemplate.objects.filter(organization=organization).count()

		# Optimize metrics queries with single aggregates
		sent_today_agg = OrgAlertRecipient.objects.filter(
			message__organization=organization,
			status='sent',
			sent_at__gte=start_today
		).aggregate(count=Count('id'))
		msgs_sent_today = sent_today_agg['count']

		sent_week_agg = OrgAlertRecipient.objects.filter(
			message__organization=organization,
			status='sent',
			sent_at__gte=start_week
		).aggregate(count=Count('id'))
		msgs_sent_week = sent_week_agg['count']

		sent_month_agg = OrgAlertRecipient.objects.filter(
			message__organization=organization,
			status='sent',
			sent_at__gte=start_month
		).aggregate(count=Count('id'))
		msgs_sent_month = sent_month_agg['count']

		# Calculate delivery rate efficiently
		total_recipients_agg = OrgAlertRecipient.objects.filter(message__organization=organization).aggregate(
			total=Count('id'),
			sent=Count('id', filter=Q(status='sent'))
		)
		total_recipients = total_recipients_agg['total']
		sent_recipients = total_recipients_agg['sent']
		delivery_rate = (sent_recipients / total_recipients * 100) if total_recipients else 0

		# Build simple 7-day trend arrays (oldest -> newest) for sparklines in the dashboard.
		# These are lightweight per-day counts derived from created_at / sent_at fields.
		from django.db.models.functions import TruncDate
		from django.db.models import Count
		trend_days = getattr(settings, 'TREND_DAYS', 7)
		now = now
		start_date = (now - datetime.timedelta(days=trend_days - 1)).date()
		# Aggregate sent counts by sent_at date
		msgs_qs = OrgAlertRecipient.objects.filter(message__organization=organization, status='sent', sent_at__date__gte=start_date).annotate(day=TruncDate('sent_at')).values('day').annotate(count=Count('id'))
		# Aggregate contacts and templates by created_at
		contacts_qs = Contact.objects.filter(organization=organization, created_at__date__gte=start_date).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id'))
		templates_qs = OrgSMSTemplate.objects.filter(organization=organization, created_at__date__gte=start_date).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id'))
		# Totals by message.created_at (denominator for delivery %)
		total_qs = OrgAlertRecipient.objects.filter(message__organization=organization, message__created_at__date__gte=start_date).annotate(day=TruncDate('message__created_at')).values('day').annotate(total=Count('id'))
		# Build lookup dicts
		msgs_by_date = { r['day']: r['count'] for r in msgs_qs }
		contacts_by_date = { r['day']: r['count'] for r in contacts_qs }
		templates_by_date = { r['day']: r['count'] for r in templates_qs }
		total_by_date = { r['day']: r['total'] for r in total_qs }
		# Build arrays oldest->newest
		msgs_sent_trend = []
		contacts_trend = []
		templates_trend = []
		delivery_trend = []
		for i in range(trend_days - 1, -1, -1):
			d = (now - datetime.timedelta(days=i)).date()
			msgs_sent_trend.append(msgs_by_date.get(d, 0))
			contacts_trend.append(contacts_by_date.get(d, 0))
			templates_trend.append(templates_by_date.get(d, 0))
			tot = total_by_date.get(d, 0)
			sent = msgs_by_date.get(d, 0)
			delivery_trend.append(int((sent / tot * 100)) if tot else 0)

		# Cache the expensive metrics for 5 minutes (but don't fail if caching is unavailable)
		try:
			cache.set(cache_key, {
				'messages': messages,
				'contacts_count': contacts_count,
				'templates_count': templates_count,
				'msgs_sent_today': msgs_sent_today,
				'msgs_sent_week': msgs_sent_week,
				'msgs_sent_month': msgs_sent_month,
				'total_recipients': total_recipients,
				'sent_recipients': sent_recipients,
				'delivery_rate': delivery_rate,
				'msgs_sent_trend': msgs_sent_trend,
				'contacts_trend': contacts_trend,
				'templates_trend': templates_trend,
				'delivery_trend': delivery_trend,
			}, getattr(settings, 'CACHE_TIMEOUT_DASHBOARD', 300))
		except Exception:
			# If caching fails, just continue without caching - don't break the application
			pass

	return render(request, "org_admin_dashboard.html", {
		"organization": organization,
		"messages": messages,
		"error": error,
		"message_sent": message_sent,
		"contacts_count": contacts_count,
		"templates_count": templates_count,
		"msgs_sent_today": msgs_sent_today,
		"msgs_sent_week": msgs_sent_week,
		"msgs_sent_month": msgs_sent_month,
		"delivery_rate": delivery_rate,
		# trend arrays for sparklines (lists of ints, oldest->newest)
		"contacts_trend": contacts_trend,
		"templates_trend": templates_trend,
		"msgs_sent_trend": msgs_sent_trend,
		"delivery_trend": delivery_trend,
		"hubtel_dry_run": getattr(settings, 'HUBTEL_DRY_RUN', False),
		"clicksend_dry_run": getattr(settings, 'CLICKSEND_DRY_RUN', False),
		"is_suspended": not organization.is_active,
		"low_balance": organization.balance < organization.get_current_sms_rate() * 10,  # Low balance if can't send 10 SMS
	})


@login_required
def enroll_tenant_view(request):
	"""Super Admin-only enroll page (separate from dashboard form).

	Creates a School or Organization and optionally an admin account. If an
	admin email is provided a password-reset email will be sent so the admin
	can set their password.
	"""
	user = request.user
	if user.role != User.SUPER_ADMIN:
		return redirect('dashboard')

	# Ensure generated_credentials is always defined so GET requests don't hit
	# an UnboundLocalError when rendering the form (POST may set this).
	notice = None
	generated_credentials = None
	prefill_data = None

	# Check for prefill parameter (approved enrollment request)
	prefill_id = request.GET.get('prefill')
	if prefill_id:
		try:
			from .models import EnrollmentRequest
			enrollment_request = EnrollmentRequest.objects.get(id=prefill_id, status='approved')
			prefill_data = {
				'id': enrollment_request.id,
				'name': enrollment_request.org_name,
				'entity_type': 'organization',  # Default to organization
				'org_type': enrollment_request.org_type,
				'contact_name': enrollment_request.contact_name,
				'email': enrollment_request.email,
				'phone_primary': enrollment_request.phone,
				'address': enrollment_request.address or '',
				'message': enrollment_request.message or '',
			}
		except EnrollmentRequest.DoesNotExist:
			notice = "Enrollment request not found or not approved."

	# Add logging import so we can record unexpected exceptions to the app logs.
	import logging

	if request.method == 'POST':
		entity_type = request.POST.get('entity_type', 'school')
		name = request.POST.get('name')
		address = request.POST.get('address')
		phone_primary = request.POST.get('phone_primary')
		phone_secondary = request.POST.get('phone_secondary')
		sender_id = request.POST.get('sender_id') or None
		admin_email = request.POST.get('admin_email')
		logo_file = request.FILES.get('logo')

		base_slug = slugify(name) if name else None
		unique_slug = base_slug
		counter = 2
		if entity_type == 'organization':
			from .models import Organization as OrgModel
			if base_slug:
				while OrgModel.objects.filter(slug=unique_slug).exists():
					unique_slug = f"{base_slug}-{counter}"
					counter += 1
			org = OrgModel.objects.create(
				name=name,
				org_type=request.POST.get('org_type', 'company'),
				slug=unique_slug,
				primary_color=request.POST.get('primary_color') or '#0d6efd',
				secondary_color=request.POST.get('secondary_color') or '#6c757d',
				clicksend_username=request.POST.get('clicksend_username'),
				clicksend_api_key=request.POST.get('clicksend_api_key'),
				sender_id=sender_id,
				address=address,
				phone_primary=phone_primary,
				phone_secondary=phone_secondary,
			)
			if logo_file:
				org.logo = logo_file
				org.save()

			# create admin account if admin_email provided or when first/last name provided
			generated_credentials = None
			if admin_email or (request.POST.get('first_name') or request.POST.get('last_name')):
				from django.contrib.auth import get_user_model
				import secrets
				UserModel = get_user_model()
				# try to build a username from first+last or from email localpart
				first = request.POST.get('first_name') or ''
				last = request.POST.get('last_name') or ''
				# Build a sensible base username; fall back to email localpart or 'user'
				base_username = (first + '.' + last).strip('.').lower() or (admin_email.split('@')[0] if admin_email else 'user')

				username = base_username
				c = 2
				while UserModel.objects.filter(username=username).exists():
					username = f"{base_username}{c}"
					c += 1

				temp_pw = secrets.token_urlsafe(10)
				new_user = UserModel.objects.create_user(username=username, email=admin_email or '', password=temp_pw)
				# set role and link to org
				new_user.role = getattr(User, 'ORG_ADMIN', 'org_admin')  # type: ignore
				new_user.organization = org  # type: ignore
				if first:
					new_user.first_name = first
				if last:
					new_user.last_name = last
				new_user.save()

				# Do NOT attempt to send password-reset email here to avoid mail backend errors in some deployments.
				# Instead, surface the generated credentials to the superadmin in the notice so they can share them.
				generated_credentials = {'username': username, 'password': temp_pw, 'email': admin_email}

			notice = f"Organization '{org.name}' created."
			if generated_credentials:
				notice += f" Admin account created: username={generated_credentials['username']}"

			# Delete the enrollment request if it was used for prefill
			if prefill_id:
				try:
					from .models import EnrollmentRequest
					EnrollmentRequest.objects.filter(id=prefill_id).delete()
				except Exception:
					pass  # Silently ignore if deletion fails

		else:
			from .models import School as SchoolModel
			if base_slug:
				while SchoolModel.objects.filter(slug=unique_slug).exists():
					unique_slug = f"{base_slug}-{counter}"
					counter += 1
			school = SchoolModel.objects.create(
				name=name,
				slug=unique_slug,
				primary_color=request.POST.get('primary_color') or '#000000',
				secondary_color=request.POST.get('secondary_color') or '#FFFFFF',
				clicksend_username=request.POST.get('clicksend_username'),
				clicksend_api_key=request.POST.get('clicksend_api_key'),
				sender_id=sender_id,
				address=address,
				phone_primary=phone_primary,
				phone_secondary=phone_secondary,
			)
			if logo_file:
				school.logo = logo_file
				school.save()

			# create admin for school similarly to org flow, but avoid sending emails here
			generated_credentials = None
			if admin_email or (request.POST.get('first_name') or request.POST.get('last_name')):
				from django.contrib.auth import get_user_model
				import secrets
				UserModel = get_user_model()
				first = request.POST.get('first_name') or ''
				last = request.POST.get('last_name') or ''
				base_username = (first + '.' + last).strip('.').lower() or (admin_email.split('@')[0] if admin_email else 'user')

				username = base_username
				c = 2
				while UserModel.objects.filter(username=username).exists():
					username = f"{base_username}{c}"
					c += 1

				temp_pw = secrets.token_urlsafe(10)
				new_user = UserModel.objects.create_user(username=username, email=admin_email or '', password=temp_pw)
				new_user.role = getattr(User, 'SCHOOL_ADMIN', 'school_admin')
				new_user.school = school
				if first:
					new_user.first_name = first
				if last:
					new_user.last_name = last
				new_user.save()
				generated_credentials = {'username': username, 'password': temp_pw, 'email': admin_email}

			notice = f"School '{school.name}' created."
			if generated_credentials:
				notice += f" Admin account created: username={generated_credentials['username']}"

			# Delete the enrollment request if it was used for prefill
			if prefill_id:
				try:
					from .models import EnrollmentRequest
					EnrollmentRequest.objects.filter(id=prefill_id).delete()
				except Exception:
					pass  # Silently ignore if deletion fails

	try:
		return render(request, 'enroll_tenant.html', {'notice': notice, 'generated_credentials': generated_credentials, 'prefill_data': prefill_data})
	except Exception:
		# Log the full traceback to the configured logger and re-raise so Django
		# still returns a 500 to the client. The logged traceback will appear in
		# Render's service logs and help diagnose the issue.
		logging.exception('Unhandled exception in enroll_tenant_view')
		raise


@login_required
def org_send_sms(request, org_slug=None):
	"""Separate send page for org admins — supports selecting contact groups."""
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	if org_slug and org.slug != org_slug:
		return redirect('org_send_sms', org_slug=org.slug)
	if not org.is_active:
		return render(request, 'org_send_sms.html', {'organization': org, 'error': 'Your organization account is suspended. Please contact support.'})

	# Load org templates for selection
	from .models import OrgSMSTemplate
	templates = OrgSMSTemplate.objects.filter(organization=org).order_by('-created_at')
	from .models import Contact, ContactGroup, OrgMessage, OrgAlertRecipient
	error = None
	success = None

	# Paginate contacts for better performance
	from django.core.paginator import Paginator
	contacts_page = request.GET.get('contacts_page', 1)
	contacts_qs = Contact.objects.filter(organization=org).order_by('name')
	contacts_paginator = Paginator(contacts_qs, 50)  # 50 contacts per page
	try:
		contacts = contacts_paginator.page(contacts_page)
	except:
		contacts = contacts_paginator.page(1)

	groups = ContactGroup.objects.filter(organization=org)

	# reCAPTCHA support: site/secret from settings
	recaptcha_site = getattr(settings, 'RECAPTCHA_SITE_KEY', None)
	recaptcha_secret = getattr(settings, 'RECAPTCHA_SECRET_KEY', None)

	if request.method == 'POST':
		# If reCAPTCHA is enabled, validate before processing the send
		if recaptcha_secret:
			token = request.POST.get('g-recaptcha-response')
			if not token:
				return render(request, 'org_send_sms.html', {'organization': org, 'contacts': contacts, 'groups': groups, 'error': 'Please complete the reCAPTCHA.', 'recaptcha_site_key': recaptcha_site, 'hubtel_dry_run': getattr(settings, 'HUBTEL_DRY_RUN', False), 'clicksend_dry_run': getattr(settings, 'CLICKSEND_DRY_RUN', False)})
			try:
				import requests
				resp = requests.post('https://www.google.com/recaptcha/api/siteverify', data={'secret': recaptcha_secret, 'response': token, 'remoteip': request.META.get('REMOTE_ADDR')}, timeout=5)
				if not resp.json().get('success'):
					return render(request, 'org_send_sms.html', {'organization': org, 'contacts': contacts, 'groups': groups, 'error': 'reCAPTCHA validation failed.', 'recaptcha_site_key': recaptcha_site, 'hubtel_dry_run': getattr(settings, 'HUBTEL_DRY_RUN', False), 'clicksend_dry_run': getattr(settings, 'CLICKSEND_DRY_RUN', False)})
			except Exception:
				return render(request, 'org_send_sms.html', {'organization': org, 'contacts': contacts, 'groups': groups, 'error': 'Could not validate reCAPTCHA.', 'recaptcha_site_key': recaptcha_site, 'hubtel_dry_run': getattr(settings, 'HUBTEL_DRY_RUN', False), 'clicksend_dry_run': getattr(settings, 'CLICKSEND_DRY_RUN', False)})
		# allow selecting a template and/or typing custom message
		template_id = request.POST.get('template_id')
		sms_body = request.POST.get('sms_body')
		if template_id and not sms_body:
			try:
				tpl = OrgSMSTemplate.objects.get(id=template_id, organization=org)
				sms_body = tpl.content
			except OrgSMSTemplate.DoesNotExist:
				pass
		scheduled_time = request.POST.get('scheduled_time')
		action = request.POST.get('action')
		selected_contacts = request.POST.getlist('contacts')
		selected_groups = request.POST.getlist('groups')

		# gather contact queryset
		if selected_contacts:
			contact_qs = Contact.objects.filter(organization=org, id__in=selected_contacts)
		else:
			contact_qs = Contact.objects.none()
		if selected_groups:
			grp_contacts = Contact.objects.filter(groups__id__in=selected_groups, organization=org)
			contact_qs = contact_qs | grp_contacts
		contact_qs = contact_qs.distinct()
		# If no explicit recipients selected, default to all contacts
		if not selected_contacts and not selected_groups:
			contact_qs = Contact.objects.filter(organization=org)

		# If action not provided (e.g., user pressed Enter), default based on presence of scheduled_time
		if not action:
			action = 'schedule' if scheduled_time else 'send_now'

		if sms_body and contact_qs.exists():
			import datetime
			from django.utils import timezone
			scheduled_dt = timezone.now()
			if scheduled_time:
				try:
					scheduled_dt = timezone.make_aware(datetime.datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M"))
				except Exception:
					scheduled_dt = timezone.now()
			msg = OrgMessage.objects.create(
				organization=org,
				content=sms_body,
				scheduled_time=scheduled_dt,
				sent=False,
				created_by=request.user,
			)
			for c in contact_qs:
				OrgAlertRecipient.objects.create(message=msg, contact=c, status='pending')
			# If action is send_now, attempt to send immediately (synchronous)
			if action == 'send_now':
				from django.utils import timezone as _tz
				from core import hubtel_utils
				from decimal import Decimal
				try:
					from core import clicksend_utils
				except Exception:
					# clicksend_client may not be installed in some deployments;
					# defer failure until (and unless) it's actually used as a fallback.
					clicksend_utils = None

				# Check package before sending
				from .utils import validate_sms_balance
				is_valid, balance_error = validate_sms_balance(org, contact_qs.count(), settings)
				if not is_valid:
					error = balance_error
				else:
					processed = 0
					for ar in getattr(msg, 'recipients_status').all():
						phone = ar.contact.phone_number
						try:
							# prefer Hubtel; fallback to ClickSend
							sent_id = None
							try:
								sent_id = hubtel_utils.send_sms(phone, sms_body, org)
							except Exception as e_hub:
								# If ClickSend integration is available, try it as a fallback.
								if clicksend_utils is not None:
									try:
										sent_id = clicksend_utils.send_sms(phone, sms_body, org)
									except Exception as e_click:
										raise Exception(f"Hubtel error: {e_hub}; ClickSend error: {e_click}")
								else:
									# No ClickSend client installed; surface the original Hubtel error.
									raise Exception(f"Hubtel error: {e_hub}; ClickSend not available")
							ar.provider_message_id = str(sent_id)
							ar.status = 'sent'
							ar.sent_at = _tz.now()
							ar.error_message = ''
							ar.save()
							processed += 1
						except Exception as e:
							import logging
							logger = logging.getLogger(__name__)
							logger.error(f"SMS sending failed for contact {ar.contact.id} ({ar.contact.phone_number}): {str(e)}")
							ar.retry_count = (ar.retry_count or 0) + 1
							ar.last_retry_at = _tz.now()
							ar.error_message = str(e)
							if ar.retry_count >= getattr(settings, 'ORG_MESSAGE_MAX_RETRIES', 3):
								ar.status = 'failed'
								logger.warning(f"SMS failed permanently for contact {ar.contact.id} after {ar.retry_count} retries")
							else:
								ar.status = 'pending'
								logger.info(f"SMS queued for retry for contact {ar.contact.id}, attempt {ar.retry_count}")
							ar.save()

					# Deduct SMS cost from balance
					sms_cost = 0
					if processed > 0:
						from .utils import deduct_sms_balance
						sms_deducted = deduct_sms_balance(org, processed, settings)
						sms_cost = org.get_current_sms_rate() * processed

					if processed > 0:
						success = f"Message sent to {processed} recipients. Cost: ₵{sms_cost:.2f} (₵{org.sms_rate:.2f} per SMS). Balance: ₵{org.balance:.2f}."
					else:
						error = 'Failed to send any messages. Please try again.'
		else:
			error = 'Please provide a message and at least one recipient.'

	return render(request, 'org_send_sms.html', {'organization': org, 'contacts': contacts, 'groups': groups, 'templates': templates, 'sms_body': request.POST.get('sms_body', ''), 'error': error, 'success': success, 'recaptcha_site_key': getattr(settings, 'RECAPTCHA_SITE_KEY', None), 'hubtel_dry_run': getattr(settings, 'HUBTEL_DRY_RUN', False), 'clicksend_dry_run': getattr(settings, 'CLICKSEND_DRY_RUN', False)})


@login_required
def org_groups_view(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	from .models import ContactGroup, Contact
	notice = None
	if request.method == 'POST':
		# create / edit / delete actions
		if request.POST.get('action') == 'create':
			name = request.POST.get('name')
			contact_ids = request.POST.getlist('contacts')
			if name:
				group = ContactGroup.objects.create(organization=org, name=name)
				if contact_ids:
					group.contacts.set(Contact.objects.filter(id__in=contact_ids, organization=org))
				notice = f"Group '{name}' created."
		elif request.POST.get('action') == 'delete':
			gid = request.POST.get('group_id')
			try:
				g = ContactGroup.objects.get(id=gid, organization=org)
				g.delete()
				notice = 'Group deleted.'
			except ContactGroup.DoesNotExist:
				notice = 'Group not found.'
		elif request.POST.get('action') == 'edit':
			gid = request.POST.get('group_id')
			name = request.POST.get('name')
			contact_ids = request.POST.getlist('contacts')
			try:
				g = ContactGroup.objects.get(id=gid, organization=org)
				if name:
					g.name = name
				if contact_ids is not None:
					g.contacts.set(Contact.objects.filter(id__in=contact_ids, organization=org))
				g.save()
				notice = 'Group updated.'
			except ContactGroup.DoesNotExist:
				notice = 'Group not found.'

	groups = ContactGroup.objects.filter(organization=org)
	contacts = Contact.objects.filter(organization=org)
	# support editing via ?edit=<group_id>
	edit_group = None
	edit_id = request.GET.get('edit')
	if edit_id:
		try:
			edit_group = ContactGroup.objects.get(id=edit_id, organization=org)
		except Exception:
			edit_group = None

	return render(request, 'org_groups.html', {'organization': org, 'groups': groups, 'contacts': contacts, 'notice': notice, 'edit_group': edit_group})


@login_required
def org_scheduled_messages(request, org_slug=None):
	# Tenant admin view: list scheduled (pending) messages for this organization
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	if org_slug and org.slug != org_slug:
		return redirect('org_scheduled_messages', org_slug=org.slug)

	from .models import OrgMessage, OrgAlertRecipient
	# Scheduled messages are those not yet marked 'sent'
	scheduled = OrgMessage.objects.filter(organization=org).filter(sent=False).order_by('-scheduled_time')
	return render(request, 'org_messages_scheduled.html', {'organization': org, 'messages': scheduled})


@login_required
def org_sent_messages(request, org_slug=None):
	# Tenant admin view: list sent messages for this organization
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	if org_slug and org.slug != org_slug:
		return redirect('org_sent_messages', org_slug=org.slug)

	from .models import OrgMessage, OrgAlertRecipient
	sent = OrgMessage.objects.filter(organization=org).filter(sent=True).order_by('-scheduled_time')
	return render(request, 'org_messages_sent.html', {'organization': org, 'messages': sent})


@login_required
def org_message_logs(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	from .models import OrgAlertRecipient
	
	# Handle delete request
	if request.method == 'POST' and 'delete_log' in request.POST:
		log_id = request.POST.get('log_id')
		try:
			log = OrgAlertRecipient.objects.get(id=log_id, message__organization=org)
			log.is_deleted = True
			log.save()
			messages.success(request, 'Message log deleted successfully.')
		except OrgAlertRecipient.DoesNotExist:
			messages.error(request, 'Log not found.')
		return redirect('org_message_logs', org_slug=org.slug)
	
	# filters
	status = request.GET.get('status')
	date_from = request.GET.get('from')
	date_to = request.GET.get('to')
	logs = OrgAlertRecipient.objects.filter(message__organization=org, is_deleted=False)
	if status:
		logs = logs.filter(status=status)
		# Parse date filter inputs (expected YYYY-MM-DD). Use sent_at__date to avoid timezone-aware/datetime issues.
		import datetime as _dt
		if date_from:
			try:
				dfrom = _dt.date.fromisoformat(date_from)
				logs = logs.filter(sent_at__date__gte=dfrom)
			except Exception:
				# ignore bad input
				date_from = None
		if date_to:
			try:
				dto = _dt.date.fromisoformat(date_to)
				logs = logs.filter(sent_at__date__lte=dto)
			except Exception:
				date_to = None
	logs = logs.order_by('-sent_at')
	return render(request, 'org_message_logs.html', {'organization': org, 'logs': logs, 'status': status, 'from': date_from, 'to': date_to})


@login_required
def org_users_view(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	from django.contrib.auth import get_user_model
	UserModel = get_user_model()
	notice = None
	if request.method == 'POST':
		# Invite user — support username-only invites (email optional).
		email = request.POST.get('email')
		username = request.POST.get('username') or (email.split('@')[0] if email else None)
		if username:
			import secrets
			temp_pw = secrets.token_urlsafe(10)
			# create user with or without email
			new_user = UserModel.objects.create_user(username=username, email=email or '', password=temp_pw)
			setattr(new_user, 'role', User.ORG_ADMIN)
			setattr(new_user, 'organization', org)
			new_user.save()
			# if email provided, send password reset so invited user can set password
			if email:
				try:
					from django.contrib.auth.forms import PasswordResetForm
					reset_form = PasswordResetForm({'email': email})
					if reset_form.is_valid():
						reset_form.save(request=request, use_https=request.is_secure(), email_template_name='registration/password_reset_email.html')
				except Exception:
					# ignore email send failures for environments without email
					pass
			notice = f"Invited {username}" 

	users = UserModel.objects.filter(organization=org)
	return render(request, 'org_users.html', {'organization': org, 'users': users, 'notice': notice})


@login_required
def org_settings_view(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	org = user.organization
	notice = None
	# Values to surface in template when we auto-create a user with a temporary password
	created_temp_pw = None
	created_username = None
	from .models import StatsViewer, SupportTicket
	# handle creating a stats-only viewer user or updating branding
	if request.method == 'POST':
		action = request.POST.get('action')
		if action == 'save_branding':
			# handle colors and sender id
			org.primary_color = request.POST.get('primary_color') or org.primary_color
			org.secondary_color = request.POST.get('secondary_color') or org.secondary_color
			org.sender_id = request.POST.get('sender_id') or org.sender_id
			# optionally handle logo upload
			if request.FILES.get('logo'):
				org.logo = request.FILES.get('logo')
			org.save()
			notice = 'Branding saved.'
		elif action == 'invite_stats_user':
			# invite or create a user who will be a stats viewer
			invite_email = request.POST.get('invite_email')
			invite_username = request.POST.get('invite_username')
			if invite_username:
				from django.contrib.auth import get_user_model
				UserModel = get_user_model()
				u = UserModel.objects.filter(username=invite_username).first()
				created = False
				temp_pw = None
				if not u:
					# create a user even if email is not provided; generate a temporary password
					import secrets
					temp_pw = secrets.token_urlsafe(12)
					# email may be blank
					u = UserModel.objects.create_user(username=invite_username, email=invite_email or '', password=temp_pw)
					created = True
				# ensure user is stats-only (not staff)
				u.is_staff = False
				u.save()
				# create StatsViewer entry
				try:
					StatsViewer.objects.get_or_create(user=u, organization=org)
					# If we created the user just now, either send a password-reset (if email) or show temp pw in notice
					if created:
						# if email not provided, surface the temporary password so admin can copy it
						if not invite_email:
							created_temp_pw = temp_pw
							created_username = invite_username
						if invite_email:
							# attempt to send password reset email rather than exposing password in UI
							try:
								from django.contrib.auth.forms import PasswordResetForm
								reset_form = PasswordResetForm({'email': invite_email})
								if reset_form.is_valid():
									reset_form.save(request=request, use_https=request.is_secure(), email_template_name='registration/password_reset_email.html')
									notice = f"Stats viewer '{invite_username}' added. Password-reset email sent to {invite_email}."
								else:
									notice = f"Stats viewer '{invite_username}' added. Temporary password: {temp_pw}"
							except Exception:
								notice = f"Stats viewer '{invite_username}' added. Temporary password: {temp_pw}"
						else:
							notice = f"Stats viewer '{invite_username}' added. Temporary password: {temp_pw}"
					else:
						notice = f"Stats viewer '{invite_username}' added."
				except Exception as e:
					notice = f"Could not add stats viewer: {e}"

		elif action == 'contact_support':
			# Create a support ticket directed to super admins
			subject = request.POST.get('subject', '').strip()
			msg = request.POST.get('message', '').strip()
			if not subject or not msg:
				notice = 'Subject and message are required.'
			else:
				SupportTicket.objects.create(organization=org, created_by=user, subject=subject, message=msg, status='open')
				# Best-effort notify via console/email if configured
				try:
					from django.core.mail import send_mail
					send_mail(subject=f"Support ticket from {org.name}: {subject}", message=msg, from_email=None, recipient_list=[getattr(settings, 'SUPPORT_EMAIL', '')] if getattr(settings, 'SUPPORT_EMAIL', '') else [])
				except Exception:
					pass
				notice = 'Your message was sent to support.'
		elif action == 'reset_password':
			# allow org admin to reset a user's password within their organization
			from django.contrib.auth import get_user_model
			UserModel = get_user_model()
			username = request.POST.get('username')
			new_password = request.POST.get('new_password')
			if not username or not new_password:
				notice = 'Username and new password are required.'
			else:
				u = UserModel.objects.filter(username=username, organization=org).first()
				if not u:
					notice = 'User not found in this organization.'
				else:
					u.set_password(new_password)
					u.save()
					notice = f"Password reset for {u.username}."
 
	# list users and stats viewers
	from django.contrib.auth import get_user_model
	UserModel = get_user_model()
	users = UserModel.objects.filter(organization=org)
	stats_viewers = StatsViewer.objects.filter(organization=org).select_related('user')
	# recent tickets for display
	tickets = SupportTicket.objects.filter(organization=org).order_by('-created_at')[:10]

	return render(request, 'org_settings.html', {
		'organization': org,
		'notice': notice,
		'users': users,
		'stats_viewers': stats_viewers,
		'tickets': tickets,
		'created_temp_pw': created_temp_pw,
		'created_username': created_username,
	})


@login_required
def org_upload_contacts(request, org_slug=None):
	# Allow ORG_ADMIN to upload contacts for their organization
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_dashboard', org_slug=organization.slug)
	if not organization.is_active:
		return render(request, 'org_contacts.html', {'organization': organization, 'error': 'Your organization account is suspended. Please contact support.'})

	message = None
	from .models import Contact
	from .utils import normalize_phone_number

	# Support multiple actions: add_contact, edit_contact, delete_contact, paste_contacts, upload_file
	if request.method == 'POST':
		action = request.POST.get('action')
		try:
			if action == 'add_contact':
				contact_id = request.POST.get('contact_id')
				name = request.POST.get('name', '').strip()
				phone = request.POST.get('phone', '').strip()
				email = request.POST.get('email', '').strip()
				if phone:
					normalized = normalize_phone_number(phone) or phone
					if contact_id:
						try:
							c = Contact.objects.get(id=contact_id, organization=organization)
							c.name = name or c.name
							c.phone_number = normalized
							c.save()
							message = 'Contact updated.'
						except Contact.DoesNotExist:
							message = 'Contact not found.'
					else:
						try:
							Contact.objects.create(organization=organization, name=name or normalized, phone_number=normalized)
							message = 'Contact added.'
						except Exception:
							message = 'Could not add contact.'
				else:
					message = 'Phone number is required.'

			elif action == 'delete_contact':
				cid = request.POST.get('contact_id')
				try:
					c = Contact.objects.get(id=cid, organization=organization)
					c.delete()
					message = 'Contact deleted.'
				except Exception:
					message = 'Could not delete contact.'

			elif action == 'paste_contacts':
				pasted = request.POST.get('pasted', '')
				created = 0
				for line in pasted.splitlines():
					parts = [p.strip() for p in line.split(',') if p.strip()]
					if not parts:
						continue
					# heuristic: last part that looks like a phone number
					phone = None
					name = None
					email = ''
					for p in parts[::-1]:
						if any(ch.isdigit() for ch in p):
							phone = p
							break
					if phone:
						name_part = parts[0] if len(parts) > 1 else ''
						name = name_part
						if len(parts) > 2:
							email = parts[2]
						normalized = normalize_phone_number(phone) or phone
						try:
							Contact.objects.create(organization=organization, name=name or normalized, phone_number=normalized)
							created += 1
						except Exception:
							pass
				message = f'Imported {created} contacts from pasted text.'

			elif action == 'upload_file':
				f = request.FILES.get('contacts_file')
				if f:
					filename = f.name.lower()
					text = ''
					if filename.endswith('.csv'):
						import csv, io
						decoded = f.read().decode('utf-8', errors='ignore')
						reader = csv.DictReader(io.StringIO(decoded))
						created = 0
						for row in reader:
							phone = (row.get('phone') or row.get('phone_number') or '').strip()
							name = (row.get('name') or row.get('contact_name') or '').strip()
							if phone:
								normalized = normalize_phone_number(phone) or phone
								try:
									Contact.objects.create(organization=organization, name=name or normalized, phone_number=normalized)
									created += 1
								except Exception:
									pass
						message = f"Imported {created} contacts from CSV."
					elif filename.endswith('.pdf'):
						try:
							import PyPDF2
							reader = PyPDF2.PdfReader(f)
							for page in reader.pages:
								text += page.extract_text() or ''
						except Exception:
							message = 'PDF parsing requires PyPDF2; please install it to enable PDF imports.'
						if text:
							import re
							phones = re.findall(r'\+?\d{7,15}', text)
							created = 0
							for p in phones:
								try:
									normalized = normalize_phone_number(p) or p
									Contact.objects.create(organization=organization, name=normalized, phone_number=normalized)
									created += 1
								except Exception:
									pass
							if created:
								message = f"Imported {created} contacts from PDF text."
					else:
						try:
							txt = f.read().decode('utf-8', errors='ignore')
						except Exception:
							txt = ''
						import re
						phones = re.findall(r'\+?\d{7,15}', txt)
						created = 0
						for p in phones:
							try:
								normalized = normalize_phone_number(p) or p
								Contact.objects.create(organization=organization, name=normalized, phone_number=normalized)
								created += 1
							except Exception:
								pass
						message = f"Imported {created} contacts from uploaded file."

			else:
				message = 'Unknown action.'
		except Exception as e:
			message = f'Import failed: {e}'

	# Prepare contacts list and optional edit target if requested
	contacts = Contact.objects.filter(organization=organization).order_by('name')
	edit_contact = None
	edit_id = request.GET.get('edit')
	if edit_id:
		try:
			edit_contact = Contact.objects.get(id=edit_id, organization=organization)
		except Exception:
			edit_contact = None

	return render(request, 'org_upload_contacts.html', {'organization': organization, 'message': message, 'contacts': contacts, 'edit_contact': edit_contact})


@login_required
def org_templates(request, org_slug=None):
	# Allow ORG_ADMIN to manage up to 5 templates
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_dashboard', org_slug=organization.slug)

	from .models import OrgSMSTemplate
	error = None
	if request.method == 'POST':
		name = request.POST.get('name')
		content = request.POST.get('content')
		templates_count = OrgSMSTemplate.objects.filter(organization=organization, is_pre_built=False).count()
		if templates_count >= 5:
			error = 'You may only create up to 5 custom templates.'
		elif not name or not content:
			error = 'Name and content are required.'
		else:
			OrgSMSTemplate.objects.create(organization=organization, name=name, content=content, is_pre_built=False)

	# Get both custom and pre-built templates
	custom_templates = OrgSMSTemplate.objects.filter(organization=organization, is_pre_built=False).order_by('-created_at')
	pre_built_templates = OrgSMSTemplate.objects.filter(organization=organization, is_pre_built=True).order_by('name')
	return render(request, 'org_templates.html', {
		'organization': organization, 
		'custom_templates': custom_templates, 
		'pre_built_templates': pre_built_templates, 
		'error': error
	})


@login_required
def org_template_edit(request, org_slug=None, template_id=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_dashboard', org_slug=organization.slug)

	from .models import OrgSMSTemplate
	try:
		tpl = OrgSMSTemplate.objects.get(id=template_id, organization=organization)
	except OrgSMSTemplate.DoesNotExist:
		return redirect('org_templates', org_slug=organization.slug)

	# Don't allow editing pre-built templates
	if tpl.is_pre_built:
		return redirect('org_templates', org_slug=organization.slug)

	error = None
	if request.method == 'POST':
		name = request.POST.get('name')
		content = request.POST.get('content')
		if not name or not content:
			error = 'Name and content are required.'
		else:
			tpl.name = name
			tpl.content = content
			tpl.save()
			return redirect('org_templates', org_slug=organization.slug)

	return render(request, 'org_template_edit.html', {'organization': organization, 'template': tpl, 'error': error})


@login_required
def org_template_delete(request, org_slug=None, template_id=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_dashboard', org_slug=organization.slug)

	from .models import OrgSMSTemplate
	try:
		tpl = OrgSMSTemplate.objects.get(id=template_id, organization=organization)
	except OrgSMSTemplate.DoesNotExist:
		return redirect('org_templates', org_slug=organization.slug)

	# Don't allow deleting pre-built templates
	if tpl.is_pre_built:
		return redirect('org_templates', org_slug=organization.slug)

	if request.method == 'POST':
		tpl.delete()
		return redirect('org_templates', org_slug=organization.slug)

	return render(request, 'org_template_delete.html', {'organization': organization, 'template': tpl})


@login_required
def org_retry_failed(request, org_slug=None):
	# Trigger retry of failed org alert recipients (best-effort)
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_dashboard', org_slug=organization.slug)

	from .models import OrgAlertRecipient, OrgMessage, Contact
	from core.hubtel_utils import send_sms
	retried = 0
	errors = []
	qs = OrgAlertRecipient.objects.filter(message__organization=organization, status='failed')
	for ar in qs:
		try:
			# attempt resend
			msg = ar.message
			contact = ar.contact
			message_id = send_sms(contact.phone_number, msg.content, organization)
			ar.status = 'sent'
			ar.sent_at = None
			ar.error_message = None
			ar.save()
			retried += 1
		except Exception as e:
			errors.append(str(e))

	return render(request, 'org_retry_result.html', {'organization': organization, 'retried': retried, 'errors': errors})


@csrf_exempt
def hubtel_webhook(request):
	"""Handle Hubtel delivery receipts (webhook).

	Hubtel may POST JSON with keys like `messageId`, `status`, `statusDescription`, `to`.
	We try to match `messageId` against `AlertRecipient.provider_message_id` and update
	the recipient status accordingly.
	"""
	if request.method != 'POST':
		return HttpResponse(status=405)

	# Verify HMAC signature if configured
	secret = getattr(settings, 'HUBTEL_WEBHOOK_SECRET', None)
	sig_header = request.META.get('HTTP_X_HUBTEL_SIGNATURE') or request.META.get('HTTP_X_HUBTEL_SIGNATURE'.lower())
	if secret:
		if not sig_header:
			return JsonResponse({'error': 'missing signature'}, status=403)
		try:
			import hmac, hashlib
			body = request.body or b''
			computed = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
			# allow either hex digest or prefixed forms
			if not hmac.compare_digest(computed, sig_header.strip()):
				return JsonResponse({'error': 'invalid signature'}, status=403)
		except Exception:
			return JsonResponse({'error': 'signature verification failed'}, status=403)

	try:
		payload = json.loads(request.body.decode('utf-8')) if request.body else {}
	except Exception:
		# fallback to form-encoded POST
		payload = request.POST.dict()

	message_id = payload.get('messageId') or payload.get('message_id') or payload.get('MessageId')
	provider_status = payload.get('status') or payload.get('statusDescription') or payload.get('deliveryStatus')

	if not message_id:
		return JsonResponse({'error': 'missing messageId'}, status=400)

	# Try to find matching recipient in either school-level AlertRecipient or org-level OrgAlertRecipient
	from .models import AlertRecipient, OrgAlertRecipient
	try:
		ar = AlertRecipient.objects.filter(provider_message_id=message_id).first()
		model_used = 'AlertRecipient'
		if not ar:
			ar = OrgAlertRecipient.objects.filter(provider_message_id=message_id).first()
			model_used = 'OrgAlertRecipient' if ar else None

		if not ar:
			return JsonResponse({'status': 'not_found'}, status=404)

		# Persist raw provider status
		ar.provider_status = provider_status or ''

		# Map provider status to internal status
		if provider_status:
			ps = str(provider_status).strip().lower()
			if ps in ('delivered', 'delivered_to_terminal', '2') or 'deliv' in ps:
				ar.status = 'sent'
			elif ps in ('failed', 'undelivered', '3') or 'fail' in ps:
				ar.status = 'failed'

		# If recipient became sent and doesn't have sent_at, set it
		try:
			from django.utils import timezone as _tz
			if getattr(ar, 'status', None) == 'sent' and not getattr(ar, 'sent_at', None):
				ar.sent_at = _tz.now()
		except Exception:
			pass

		ar.save()
		return JsonResponse({'status': 'updated', 'model': model_used})
	except Exception as e:
		import logging
		logger = logging.getLogger(__name__)
		logger.exception('Error processing Hubtel webhook')
		return JsonResponse({'error': str(e)}, status=500)





@login_required
def org_billing(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_billing', org_slug=organization.slug)

	message = None
	paystack_public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', None)

	if request.method == 'POST':
		action = request.POST.get('action')
		is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
		
		if action == 'top_up_balance':
			amount = Decimal(request.POST.get('amount', '0'))
			if amount > 0:
				# In a real implementation, this would integrate with Paystack
				# For now, we'll simulate balance top-up
				organization.balance += amount
				organization.save()
				message = f'Balance topped up successfully! ₵{amount:.2f} added. New balance: ₵{organization.balance:.2f}.'
				if is_ajax:
					return JsonResponse({'success': True, 'message': message})
			else:
				message = 'Invalid amount.'
				if is_ajax:
					return JsonResponse({'success': False, 'message': message})

	from .models import Package
	sms_customer_rate = getattr(settings, 'SMS_CUSTOMER_RATE', Decimal('0.10'))
	sms_provider_cost = getattr(settings, 'SMS_PROVIDER_COST', Decimal('0.03'))
	sms_min_balance = getattr(settings, 'SMS_MIN_BALANCE', Decimal('1.00'))

	return render(request, 'org_billing.html', {
		'organization': organization,
		'user': user,
		'message': message,
		'paystack_public_key': paystack_public_key,
		'sms_customer_rate': sms_customer_rate,
		'sms_provider_cost': sms_provider_cost,
		'sms_min_balance': sms_min_balance,
		'current_sms_rate': organization.get_current_sms_rate(),
		'total_sms_sent': organization.total_sms_sent,
		'max_payment_amount': getattr(settings, 'MAX_PAYMENT_AMOUNT', Decimal('10000')),
		'min_payment_amount': getattr(settings, 'MIN_PAYMENT_AMOUNT', Decimal('0.01')),
	})


def org_billing_callback(request, org_slug=None):
	# Get organization from slug
	try:
		organization = Organization.objects.get(slug=org_slug)
	except Organization.DoesNotExist:
		if request.method == "POST":
			return JsonResponse({'success': False, 'message': 'Organization not found'}, status=404)
		return redirect('home')

	paystack_public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', None)
	message = None

	# Handle AJAX verification from inline Paystack popup
	if request.method == "POST":
		reference = request.POST.get('reference')
		if not reference:
			return JsonResponse({'success': False, 'message': 'Missing payment reference'}, status=400)
		try:
			from . import paystack_utils
			verification = paystack_utils.verify_payment(reference)
			data = verification.get('data', {}) or {}
			status = data.get('status')
			amount_raw = data.get('amount')
			amount = Decimal(amount_raw or 0) / 100
			tx_id = data.get('id')

			from .models import Payment
			from django.utils import timezone
			if status == 'success' and amount > 0:
				with transaction.atomic():
					payment, created = Payment.objects.select_for_update().get_or_create(
						paystack_reference=reference,
						defaults={
							'organization': organization,
							'amount': amount,
							'paystack_transaction_id': tx_id,
							'status': 'success',
							'processed_at': timezone.now(),
						}
					)
					if created:
						organization.balance = (organization.balance or Decimal('0')) + amount
						organization.save(update_fields=['balance'])
				return JsonResponse({'success': True, 'message': 'Payment verified', 'balance': str(organization.balance)})

			# record failed attempt if not already stored
			Payment.objects.get_or_create(
				paystack_reference=reference,
				defaults={
					'organization': organization,
					'amount': amount,
					'paystack_transaction_id': tx_id,
					'status': status or 'failed',
					'processed_at': timezone.now(),
				}
			)
			return JsonResponse({'success': False, 'message': 'Payment not successful', 'status': status}, status=400)
		except Exception as e:
			return JsonResponse({'success': False, 'message': str(e)}, status=500)

	# Fallback GET handling (e.g., if Paystack redirects)
	reference = request.GET.get('reference')
	if reference:
		try:
			from . import paystack_utils
			verification = paystack_utils.verify_payment(reference)
			data = verification.get('data', {}) or {}
			if data.get('status') == 'success':
				amount = Decimal(data.get('amount', 0)) / 100
				if amount > 0:
					from .models import Payment
					from django.utils import timezone
					payment, created = Payment.objects.get_or_create(
						paystack_reference=reference,
						defaults={
							'organization': organization,
							'amount': amount,
							'paystack_transaction_id': data.get('id'),
							'status': 'success',
							'processed_at': timezone.now(),
						}
					)
					if created:
						organization.balance += amount
						organization.save(update_fields=['balance'])
						message = f'Payment successful! Balance added: GHS {amount}. New balance: GHS {organization.balance}'
					else:
						message = f'Payment already processed. Current balance: GHS {organization.balance}'
				else:
					message = 'Payment successful but amount not found.'
			else:
				message = 'Payment was not successful.'
		except Exception as e:
			message = f'Payment verification failed: {str(e)}'
	else:
		message = 'No payment reference found.'

	sms_customer_rate = getattr(settings, 'SMS_CUSTOMER_RATE', Decimal('0.10'))
	sms_provider_cost = getattr(settings, 'SMS_PROVIDER_COST', Decimal('0.03'))
	sms_min_balance = getattr(settings, 'SMS_MIN_BALANCE', Decimal('1.00'))

	return render(request, 'org_billing.html', {
		'organization': organization,
		'balance': organization.balance,
		'sms_customer_rate': sms_customer_rate,
		'sms_provider_cost': sms_provider_cost,
		'sms_min_balance': sms_min_balance,
		'paystack_public_key': paystack_public_key,
		'message': message,
		'callback_mode': True,  # Flag to indicate this is a callback response
	})


@login_required
def super_payments_view(request):
    """Superadmin view for payment analytics and transaction history."""
    user = request.user
    if not user.role == User.SUPER_ADMIN:
        return redirect('dashboard')

    from .models import Payment, Organization
    from django.db.models import Sum, Count
    from django.core.paginator import Paginator
    from decimal import Decimal

    # Get filter parameters
    status_filter = request.GET.get('status', '')
    org_filter = request.GET.get('org', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Base queryset
    payments = Payment.objects.select_related('organization').order_by('-created_at')

    # Apply filters
    if status_filter:
        payments = payments.filter(status=status_filter)
    if org_filter:
        payments = payments.filter(organization__slug=org_filter)

    # Date filtering
    if date_from:
        payments = payments.filter(created_at__date__gte=date_from)
    if date_to:
        payments = payments.filter(created_at__date__lte=date_to)

    # Pagination
    paginator = Paginator(payments, 50)  # 50 payments per page
    page_number = request.GET.get('page')
    payments_page = paginator.get_page(page_number)

    # Summary statistics
    total_payments = Payment.objects.filter(status='success').count()
    total_revenue = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    pending_payments = Payment.objects.filter(status='pending').count()
    failed_payments = Payment.objects.filter(status='failed').count()

    # Recent payments (last 30 days)
    from django.utils import timezone
    import datetime
    thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
    recent_revenue = Payment.objects.filter(
        status='success',
        created_at__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Organizations with payments
    orgs_with_payments = Organization.objects.filter(payments__status='success').distinct().order_by('name')

    context = {
        'payments': payments_page,
        'total_payments': total_payments,
        'total_revenue': total_revenue,
        'pending_payments': pending_payments,
        'failed_payments': failed_payments,
        'recent_revenue': recent_revenue,
        'orgs_with_payments': orgs_with_payments,
        'status_filter': status_filter,
        'org_filter': org_filter,
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(request, 'super_payments.html', context)


# Package Management Views
@login_required
@user_passes_test(lambda u: u.is_superuser)
def super_packages_view(request):
    """Superadmin view for managing SMS packages"""
    packages = Package.objects.all().order_by('-created_at')
    message = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_active':
            package_id = request.POST.get('package_id')
            try:
                package = Package.objects.get(id=package_id)
                package.is_active = not package.is_active
                package.save()
                message = f'Package "{package.name}" {"activated" if package.is_active else "deactivated"} successfully.'
            except Package.DoesNotExist:
                message = 'Package not found.'

    context = {
        'packages': packages,
        'message': message,
    }
    return render(request, 'super_packages.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_package_view(request):
    """Create a new SMS package"""
    message = None

    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            description = request.POST.get('description')
            price = Decimal(request.POST.get('price'))
            sms_count = int(request.POST.get('sms_count'))
            expiry_days = int(request.POST.get('expiry_days', 0))
            package_type = request.POST.get('package_type')
            is_premium = request.POST.get('is_premium') == 'on'

            package = Package.objects.create(
                name=name,
                description=description,
                price=price,
                sms_count=sms_count,
                expiry_days=expiry_days,
                package_type=package_type,
                is_premium=is_premium,
                is_active=True
            )
            message = f'Package "{package.name}" created successfully!'
            return redirect('super_packages')
        except Exception as e:
            message = f'Error creating package: {str(e)}'

    context = {
        'message': message,
        'package_types': Package.PACKAGE_TYPE_CHOICES,
    }
    return render(request, 'create_package.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_package_view(request, package_id):
    """Edit an existing SMS package"""
    try:
        package = Package.objects.get(id=package_id)
    except Package.DoesNotExist:
        return redirect('super_packages')

    message = None

    if request.method == 'POST':
        try:
            package.name = request.POST.get('name')
            package.description = request.POST.get('description')
            package.price = Decimal(request.POST.get('price'))
            package.sms_count = int(request.POST.get('sms_count'))
            package.expiry_days = int(request.POST.get('expiry_days', 0))
            package.package_type = request.POST.get('package_type')
            package.is_premium = request.POST.get('is_premium') == 'on'
            package.save()
            message = f'Package "{package.name}" updated successfully!'
            return redirect('super_packages')
        except Exception as e:
            message = f'Error updating package: {str(e)}'

    context = {
        'package': package,
        'message': message,
        'package_types': Package.PACKAGE_TYPE_CHOICES,
    }
    return render(request, 'edit_package.html', context)