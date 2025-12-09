import time
import signal
import sys
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
import os

# Simple long-running scheduler that periodically runs the send-scheduled/ pending commands.
# Intended to run as a background worker (e.g., Render background service) or via supervisor.
# Usage:
#   python manage.py run_scheduler --interval 60

RUNNING = True


def _signal_handler(signum, frame):
    global RUNNING
    RUNNING = False


class Command(BaseCommand):
    help = 'Run a simple scheduler loop that processes scheduled and pending messages.'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=int(os.environ.get('SCHEDULER_INTERVAL', 60)), help='Seconds between scheduler runs')
        parser.add_argument('--limit', type=int, default=200, help='Max recipients to process per run (passed to pending command)')
        parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode (do not perform external sends)')
        parser.add_argument('--org', type=str, help='Optional org slug to limit processing')

    def handle(self, *args, **options):
        global RUNNING
        interval = options.get('interval') or 60
        limit = options.get('limit')
        dry_run = options.get('dry_run')
        org = options.get('org')

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        self.stdout.write(self.style.SUCCESS(f'Starting scheduler loop (interval={interval}s, limit={limit}, dry_run={dry_run})'))

        while RUNNING:
            now = timezone.now()
            try:
                # 1) process any org message recipients that are pending and due
                pending_args = ['send_pending_org_messages', f'--limit={limit}']
                if dry_run:
                    pending_args.append('--dry-run')
                if org:
                    pending_args.append(f'--org={org}')
                self.stdout.write(self.style.NOTICE(f'[{now}] Running send_pending_org_messages...'))
                call_command('send_pending_org_messages', *([f'--limit={limit}'] + (['--dry-run'] if dry_run else []) + ([f'--org={org}'] if org else [])))

                # 2) process any queued school messages
                self.stdout.write(self.style.NOTICE(f'[{now}] Running send_scheduled_messages...'))
                call_command('send_scheduled_messages')

                # 3) process any queued org scheduled messages as well (safe to call twice)
                self.stdout.write(self.style.NOTICE(f'[{now}] Running send_scheduled_org_messages...'))
                call_command('send_scheduled_org_messages')

            except Exception as e:
                self.stderr.write(f'Scheduler loop error: {e}')

            # Sleep until next run or until signalled to stop
            slept = 0
            while RUNNING and slept < interval:
                time.sleep(1)
                slept += 1

        self.stdout.write(self.style.SUCCESS('Scheduler stopping gracefully.'))
