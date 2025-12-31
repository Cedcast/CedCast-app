from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Sender, SenderAssignment, Organization
from core.utils.crypto_utils import encrypt_value


class Command(BaseCommand):
    help = 'Set up test senders and assignments for the sender pool system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-senders',
            action='store_true',
            help='Create test senders with settings-based credentials',
        )
        parser.add_argument(
            '--assign-to-orgs',
            action='store_true',
            help='Assign senders to all organizations',
        )
        parser.add_argument(
            '--org-slug',
            type=str,
            help='Specific organization slug to assign sender to',
        )

    def handle(self, *args, **options):
        if options['create_senders']:
            self.create_test_senders()
        
        if options['assign_to_orgs']:
            if options['org_slug']:
                self.assign_to_organization(options['org_slug'])
            else:
                self.assign_to_all_organizations()

    def create_test_senders(self):
        """Create test senders using settings-based credentials"""
        self.stdout.write('Creating test senders...')
        
        # Hubtel sender
        hubtel_sender, created = Sender.objects.get_or_create(
            sender_id='HUBTEL_TEST',
            defaults={
                'name': 'Hubtel Test Sender',
                'sender_type': 'alphanumeric',
                'provider': 'hubtel',
                'status': 'available',
                'hubtel_api_url': getattr(settings, 'HUBTEL_API_URL', ''),
                'hubtel_client_id': encrypt_value(getattr(settings, 'HUBTEL_CLIENT_ID', '')),
                'hubtel_client_secret': encrypt_value(getattr(settings, 'HUBTEL_CLIENT_SECRET', '') or getattr(settings, 'HUBTEL_API_KEY', '')),
                'gateway_balance': 1000.00,  # Test balance
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Hubtel sender: {hubtel_sender}'))
        else:
            self.stdout.write(f'Hubtel sender already exists: {hubtel_sender}')

        # ClickSend sender
        clicksend_sender, created = Sender.objects.get_or_create(
            sender_id='CLICKSEND_TEST',
            defaults={
                'name': 'ClickSend Test Sender',
                'sender_type': 'alphanumeric',
                'provider': 'clicksend',
                'status': 'available',
                'clicksend_username': encrypt_value(getattr(settings, 'CLICKSEND_USERNAME', '')),
                'clicksend_api_key': encrypt_value(getattr(settings, 'CLICKSEND_API_KEY', '')),
                'gateway_balance': 1000.00,  # Test balance
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created ClickSend sender: {clicksend_sender}'))
        else:
            self.stdout.write(f'ClickSend sender already exists: {clicksend_sender}')

    def assign_to_all_organizations(self):
        """Assign senders to all organizations"""
        self.stdout.write('Assigning senders to all organizations...')
        
        organizations = Organization.objects.filter(is_active=True)
        hubtel_sender = Sender.objects.filter(provider='hubtel', status='available').first()
        clicksend_sender = Sender.objects.filter(provider='clicksend', status='available').first()
        
        if not hubtel_sender and not clicksend_sender:
            self.stdout.write(self.style.ERROR('No senders available. Run with --create-senders first.'))
            return
        
        for org in organizations:
            # Prefer Hubtel, fallback to ClickSend
            sender = hubtel_sender or clicksend_sender
            
            assignment, created = SenderAssignment.objects.get_or_create(
                sender=sender,
                organization=org,
                defaults={'is_active': True}
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Assigned {sender.name} to {org.name}'))
            else:
                self.stdout.write(f'Assignment already exists: {sender.name} -> {org.name}')

    def assign_to_organization(self, org_slug):
        """Assign sender to specific organization"""
        try:
            org = Organization.objects.get(slug=org_slug, is_active=True)
        except Organization.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Organization with slug "{org_slug}" not found'))
            return
        
        hubtel_sender = Sender.objects.filter(provider='hubtel', status='available').first()
        clicksend_sender = Sender.objects.filter(provider='clicksend', status='available').first()
        
        if not hubtel_sender and not clicksend_sender:
            self.stdout.write(self.style.ERROR('No senders available. Run with --create-senders first.'))
            return
        
        # Prefer Hubtel, fallback to ClickSend
        sender = hubtel_sender or clicksend_sender
        
        assignment, created = SenderAssignment.objects.get_or_create(
            sender=sender,
            organization=org,
            defaults={'is_active': True}
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Assigned {sender.name} to {org.name}'))
        else:
            self.stdout.write(f'Assignment already exists: {sender.name} -> {org.name}')