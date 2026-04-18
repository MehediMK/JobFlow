from django.core.management.base import BaseCommand

from tracker.utils import send_due_reminders


class Command(BaseCommand):
    help = 'Send due reminder emails for application deadlines, follow-ups, interviews, and expiring documents.'

    def handle(self, *args, **options):
        sent_count = send_due_reminders()
        self.stdout.write(self.style.SUCCESS(f'Sent {sent_count} reminder(s).'))
