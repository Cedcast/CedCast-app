def home_view(request):
	return render(request, "home.html")
from django.conf import settings
from core.hubtel_utils import send_sms
from django.utils.text import slugify
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import User, School
from django.http import JsonResponse, HttpResponse
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
import json
import os


def health(request):
	"""Simple health check endpoint for Render and load balancers."""
	return HttpResponse("OK", status=200)

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
				for parent in parents:
					# try to capture provider message id when sending from the UI
					try:
						message_id = send_sms(parent.phone_number, sms_body, school)
						# best-effort: if there's an AlertRecipient for this message, save it
						from .models import AlertRecipient
						ar_qs = AlertRecipient.objects.filter(parent=parent, message__content=sms_body).order_by('-id')
						if ar_qs.exists():
							ar = ar_qs.first()
							ar.provider_message_id = message_id
							ar.save()
					except Exception:
						# ignore per-recipient failures in the UI loop
						pass
				message_sent = True
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
			if user.role == User.SUPER_ADMIN:
				return redirect("dashboard")
			elif user.role == User.SCHOOL_ADMIN and user.school:
				return redirect("school_dashboard", school_slug=user.school.slug)
			elif user.role == User.ORG_ADMIN and getattr(user, 'organization', None):
				return redirect("org_dashboard", org_slug=user.organization.slug)
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
			if user.role == User.SUPER_ADMIN:
				return redirect("dashboard")
			elif user.role == User.SCHOOL_ADMIN and getattr(user, 'school', None):
				return redirect("school_dashboard", school_slug=user.school.slug)
			elif user.role == User.ORG_ADMIN and getattr(user, 'organization', None):
				return redirect("org_dashboard", org_slug=user.organization.slug)
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
			sender_display = decrypt_value(org.sender_id) if getattr(org, 'sender_id', None) else None
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

		context = {"schools": schools, "school_stats": school_stats, "org_stats": org_stats, "notice": notice,
			"total_messages": total_msgs, "total_sent": total_sent,
			"messages_trend": messages_trend, "orgs_trend": orgs_trend, "delivery_trend": delivery_trend,
			"hubtel_dry_run": getattr(settings, 'HUBTEL_DRY_RUN', False),
			"clicksend_dry_run": getattr(settings, 'CLICKSEND_DRY_RUN', False),
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
def system_logs_view(request):
    # Super Admin only
    if not request.user.role == User.SUPER_ADMIN:
        return redirect('dashboard')
    # Use Django admin LogEntry to show recent admin actions
    from django.contrib.admin.models import LogEntry
    logs = LogEntry.objects.all().order_by('-action_time')[:200]
    return render(request, 'system_logs.html', {'logs': logs})


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
	messages = OrgMessage.objects.filter(organization=organization).order_by('-scheduled_time')
	# compute org-level metrics for dashboard
	from django.utils import timezone
	import datetime
	from .models import OrgAlertRecipient, OrgSMSTemplate, Contact

	now = timezone.now()
	start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
	start_week = now - datetime.timedelta(days=7)
	start_month = now - datetime.timedelta(days=30)

	contacts_count = Contact.objects.filter(organization=organization).count()
	templates_count = OrgSMSTemplate.objects.filter(organization=organization).count()

	msgs_sent_today = OrgAlertRecipient.objects.filter(message__organization=organization, status='sent', sent_at__gte=start_today).count()
	msgs_sent_week = OrgAlertRecipient.objects.filter(message__organization=organization, status='sent', sent_at__gte=start_week).count()
	msgs_sent_month = OrgAlertRecipient.objects.filter(message__organization=organization, status='sent', sent_at__gte=start_month).count()

	total_recipients = OrgAlertRecipient.objects.filter(message__organization=organization).count()
	sent_recipients = OrgAlertRecipient.objects.filter(message__organization=organization, status='sent').count()
	delivery_rate = (sent_recipients / total_recipients * 100) if total_recipients else 0

	# Build simple 7-day trend arrays (oldest -> newest) for sparklines in the dashboard.
	# These are lightweight per-day counts derived from created_at / sent_at fields.
	from django.db.models.functions import TruncDate
	from django.db.models import Count
	trend_days = 7
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
		"low_balance": organization.balance < Decimal('10.00'),
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
				new_user.role = getattr(User, 'ORG_ADMIN', 'org_admin')
				new_user.organization = org
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

	try:
		return render(request, 'enroll_tenant.html', {'notice': notice, 'generated_credentials': generated_credentials})
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
	contacts = Contact.objects.filter(organization=org)
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
				try:
					from core import clicksend_utils
				except Exception:
					# clicksend_client may not be installed in some deployments;
					# defer failure until (and unless) it's actually used as a fallback.
					clicksend_utils = None
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
						ar.retry_count = (ar.retry_count or 0) + 1
						ar.last_retry_at = _tz.now()
						ar.error_message = str(e)
						if ar.retry_count >= getattr(settings, 'ORG_MESSAGE_MAX_RETRIES', 3):
							ar.status = 'failed'
						else:
							ar.status = 'pending'
						ar.save()
			# mark message.sent if no pending recipients
			pending_exists = getattr(msg, 'recipients_status').filter(status='pending').exists()
			if not pending_exists:
				msg.sent = True
				msg.save()
				success = f"Message sent to {processed} recipients."
			else:
				success = 'Message scheduled.'
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
	# filters
	status = request.GET.get('status')
	date_from = request.GET.get('from')
	date_to = request.GET.get('to')
	logs = OrgAlertRecipient.objects.filter(message__organization=org)
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
		templates_count = OrgSMSTemplate.objects.filter(organization=organization).count()
		if templates_count >= 5:
			error = 'You may only create up to 5 templates.'
		elif not name or not content:
			error = 'Name and content are required.'
		else:
			OrgSMSTemplate.objects.create(organization=organization, name=name, content=content)

	templates = OrgSMSTemplate.objects.filter(organization=organization).order_by('-created_at')
	return render(request, 'org_templates.html', {'organization': organization, 'templates': templates, 'error': error})


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


def signup_request(request):
	if request.method == 'POST':
		org_name = request.POST.get('org_name')
		contact_name = request.POST.get('contact_name')
		email = request.POST.get('email')
		phone = request.POST.get('phone')
		message = request.POST.get('message', '')

		# Create a support ticket or send email to superadmin
		from .models import SupportTicket
		ticket = SupportTicket.objects.create(
			organization=None,  # No org yet
			created_by=None,
			subject=f"Signup Request: {org_name}",
			message=f"Organization: {org_name}\nContact: {contact_name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}"
		)

		# Optionally send email
		try:
			from django.core.mail import send_mail
			send_mail(
				'New Signup Request',
				f"A new signup request has been submitted.\n\n{ticket.message}",
				'noreply@cedcast.com',  # From
				['superadmin@cedcast.com'],  # To superadmin
				fail_silently=True
			)
		except Exception:
			pass

		return render(request, 'signup_success.html', {'message': 'Your signup request has been submitted. We will contact you soon!'})

	return redirect('home')


@login_required
def org_billing(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect('dashboard')
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect('org_billing', org_slug=organization.slug)

	message = None
	if request.method == 'POST':
		action = request.POST.get('action')
		if action == 'add_balance':
			amount_str = request.POST.get('amount', '').strip()
			try:
				amount = Decimal(amount_str)
				if amount > 0:
					organization.balance += amount
					organization.save()
					message = f'Balance added successfully. New balance: GHS {organization.balance}'
				else:
					message = 'Amount must be positive.'
			except Exception:
				message = 'Invalid amount.'

	return render(request, 'org_billing.html', {
		'organization': organization,
		'message': message,
	})
