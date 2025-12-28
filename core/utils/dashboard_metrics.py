"""
Dashboard utilities for calculating metrics and trends.
"""
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from ..models import Organization, Contact, OrgSMSTemplate, OrgAlertRecipient, OrgMessage


class OrganizationDashboardMetrics:
	"""Service class for calculating organization dashboard metrics"""

	def __init__(self, organization):
		self.organization = organization
		self.cache_timeout = 300  # 5 minutes

	def get_cache_key(self):
		return f"org_dashboard_metrics_{self.organization.id}"

	def get_cached_metrics(self):
		"""Try to get cached metrics"""
		try:
			return cache.get(self.get_cache_key())
		except Exception:
			return None

	def cache_metrics(self, metrics):
		"""Cache metrics if caching is available"""
		try:
			cache.set(self.get_cache_key(), metrics, self.cache_timeout)
		except Exception:
			pass  # Silently fail if caching is unavailable

	def calculate_basic_metrics(self):
		"""Calculate basic organization metrics"""
		return {
			'contacts_count': self.organization.get_contacts_count(),
			'templates_count': self.organization.get_templates_count(),
			'messages_count': self.organization.get_messages_count(),
		}

	def calculate_sms_stats(self):
		"""Calculate SMS sending statistics"""
		now = timezone.now()
		start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
		start_week = now - timezone.timedelta(days=7)
		start_month = now - timezone.timedelta(days=30)

		# Use efficient aggregation queries
		stats = OrgAlertRecipient.objects.filter(
			message__organization=self.organization
		).aggregate(
			sent_today=Count('id', filter=Q(status='sent', sent_at__gte=start_today)),
			sent_week=Count('id', filter=Q(status='sent', sent_at__gte=start_week)),
			sent_month=Count('id', filter=Q(status='sent', sent_at__gte=start_month)),
		)

		return {
			'msgs_sent_today': stats['sent_today'],
			'msgs_sent_week': stats['sent_week'],
			'msgs_sent_month': stats['sent_month'],
		}

	def calculate_delivery_stats(self):
		"""Calculate delivery rate statistics"""
		return self.organization.get_delivery_stats()

	def calculate_trends(self, days=7):
		"""Calculate trend data for sparklines"""
		now = timezone.now()
		start_date = (now - timezone.timedelta(days=days - 1)).date()

		# Aggregate data by date for trends
		msgs_qs = OrgAlertRecipient.objects.filter(
			message__organization=self.organization,
			status='sent',
			sent_at__date__gte=start_date
		).annotate(day=TruncDate('sent_at')).values('day').annotate(count=Count('id'))

		contacts_qs = Contact.objects.filter(
			organization=self.organization,
			created_at__date__gte=start_date
		).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id'))

		templates_qs = OrgSMSTemplate.objects.filter(
			organization=self.organization,
			created_at__date__gte=start_date
		).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id'))

		total_qs = OrgAlertRecipient.objects.filter(
			message__organization=self.organization,
			message__created_at__date__gte=start_date
		).annotate(day=TruncDate('message__created_at')).values('day').annotate(total=Count('id'))

		# Build lookup dictionaries
		msgs_by_date = {r['day']: r['count'] for r in msgs_qs}
		contacts_by_date = {r['day']: r['count'] for r in contacts_qs}
		templates_by_date = {r['day']: r['count'] for r in templates_qs}
		total_by_date = {r['day']: r['total'] for r in total_qs}

		# Build trend arrays (oldest to newest)
		msgs_sent_trend = []
		contacts_trend = []
		templates_trend = []
		delivery_trend = []

		for i in range(days - 1, -1, -1):
			date = (now - timezone.timedelta(days=i)).date()
			msgs_sent_trend.append(msgs_by_date.get(date, 0))
			contacts_trend.append(contacts_by_date.get(date, 0))
			templates_trend.append(templates_by_date.get(date, 0))

			total = total_by_date.get(date, 0)
			sent = msgs_by_date.get(date, 0)
			delivery_trend.append(int((sent / total * 100)) if total else 0)

		return {
			'msgs_sent_trend': msgs_sent_trend,
			'contacts_trend': contacts_trend,
			'templates_trend': templates_trend,
			'delivery_trend': delivery_trend,
		}

	def get_recent_messages(self, limit=10):
		"""Get recent messages for the organization"""
		return OrgMessage.objects.filter(
			organization=self.organization
		).select_related('created_by').order_by('-scheduled_time')[:limit]

	def get_all_metrics(self):
		"""Get all dashboard metrics, using cache when possible"""
		cached = self.get_cached_metrics()
		if cached:
			# Still need to get fresh messages as they change frequently
			cached['messages'] = self.get_recent_messages()
			return cached

		# Calculate fresh metrics
		metrics = {}
		metrics.update(self.calculate_basic_metrics())
		metrics.update(self.calculate_sms_stats())
		metrics.update(self.calculate_delivery_stats())
		metrics.update(self.calculate_trends())
		metrics['messages'] = self.get_recent_messages()

		# Cache the expensive calculations
		self.cache_metrics(metrics)

		return metrics