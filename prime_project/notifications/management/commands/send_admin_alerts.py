from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.admin_email import safely_deliver
from notifications.models import AdminEmailDelivery


class Command(BaseCommand):
    help = 'Send due pending/failed admin alerts. Uses the configured Django email backend.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Maximum due rows to process (default 100).')

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 1000:
            raise CommandError('--limit must be between 1 and 1000.')
        ids = list(AdminEmailDelivery.objects.filter(
            status__in=['pending', 'failed'], next_attempt_at__lte=timezone.now(),
        ).order_by('next_attempt_at', 'pk').values_list('pk', flat=True)[:limit])
        completed = sum(bool(safely_deliver(pk)) for pk in ids)
        self.stdout.write(f'Processed {len(ids)} due record(s); {completed} accepted by the configured email backend. See Admin email deliveries for statuses.')
