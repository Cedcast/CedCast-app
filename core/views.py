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
from django.views.decorators.csrf import csrf_exempt
import json

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
		parents = school.parent_set.all()
		if selected_class:
			# Filter parents whose wards are in the selected class
			from .models import Ward
			parent_ids = Ward.objects.filter(school=school, student_class=selected_class).values_list("parent_id", flat=True).distinct()
			parents = parents.filter(id__in=parent_ids)
			sent_class = selected_class
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

def logout_view(request):
	logout(request)
	return redirect("login")

@login_required
def dashboard(request, school_slug=None):
	user = request.user
	if user.role == User.SUPER_ADMIN:
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
			org_stats.append({
				'organization': org,
				'total_messages': total_messages,
				'sent_messages': sent_messages,
				'total_recipients': total_recipients,
				'sent_recipients': sent_recipients,
				'failed_recipients': failed_recipients,
				'delivery_rate': delivery_rate,
			})
		return render(request, "super_admin_dashboard.html", {"schools": schools, "school_stats": school_stats, "org_stats": org_stats})
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
def org_dashboard(request, org_slug=None):
	user = request.user
	if user.role != User.ORG_ADMIN or not getattr(user, 'organization', None):
		return redirect("dashboard")
	organization = user.organization
	if org_slug and organization.slug != org_slug:
		return redirect("org_dashboard", org_slug=organization.slug)

	message_sent = False
	error = None
	if request.method == "POST":
		from .models import Contact, OrgMessage, OrgAlertRecipient
		# Add contact
		contact_name = request.POST.get("contact_name")
		contact_phone = request.POST.get("contact_phone")
		sms_body = request.POST.get("sms_body")
		scheduled_time = request.POST.get("scheduled_time")
		recipients_str = request.POST.get("recipients")

		if contact_name and contact_phone:
			Contact.objects.create(organization=organization, name=contact_name, phone_number=contact_phone)
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
	return render(request, "org_admin_dashboard.html", {
		"organization": organization,
		"messages": messages,
		"error": error,
		"message_sent": message_sent,
	})


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

	# Try to find matching AlertRecipient
	from .models import AlertRecipient
	try:
		ar = AlertRecipient.objects.filter(provider_message_id=message_id).first()
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

		ar.save()
		return JsonResponse({'status': 'updated'})
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)
