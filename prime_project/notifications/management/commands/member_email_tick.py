from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.campaigns import MAX_ATTEMPTS, discover_automatic_campaigns, queue_campaign, deliver_member_email, reconcile_completed_campaigns
from notifications.models import MemberEmailCampaign, MemberEmailDelivery
from notifications.models import MemberActivityDelivery
from notifications.activity_email import deliver_activity_email
from notifications.league_activity import process_pending_league_events


class Command(BaseCommand):
    help = 'Discover new enabled publications, queue scheduled opt-in campaigns, and send a bounded batch.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--queue-only', action='store_true')

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 1000:
            raise CommandError('--limit must be between 1 and 1000.')
        events = process_pending_league_events(limit=limit)
        activity_delivered = 0
        if getattr(settings, 'MEMBER_ACTIVITY_EMAIL_ENABLED', False) and not options['queue_only']:
            ids = list(MemberActivityDelivery.objects.filter(
                status__in=['pending', 'failed'], next_attempt_at__lte=timezone.now(), attempts__lt=MAX_ATTEMPTS,
            ).order_by('next_attempt_at', 'pk').values_list('pk', flat=True)[:limit])
            for pk in ids:
                activity_delivered += int(deliver_activity_email(pk))
        self.stdout.write(f'Processed {events} league event(s); sent/captured {activity_delivered} activity email(s).')
        if not getattr(settings, 'MEMBER_EMAIL_ENABLED', False):
            self.stdout.write('Member email delivery is disabled; no campaigns queued or sent.')
            return
        reconcile_completed_campaigns(limit=limit)
        try:
            discovered = discover_automatic_campaigns(limit=limit)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        queued = 0
        for pk in MemberEmailCampaign.objects.filter(status='scheduled', scheduled_at__lte=timezone.now()).order_by('scheduled_at', 'pk').values_list('pk', flat=True)[:limit]:
            queued += queue_campaign(pk)
        delivered = 0
        if not options['queue_only']:
            ids = list(MemberEmailDelivery.objects.filter(
                status__in=['pending', 'failed'], next_attempt_at__lte=timezone.now(), attempts__lt=MAX_ATTEMPTS,
            ).order_by('next_attempt_at', 'pk').values_list('pk', flat=True)[:limit])
            for pk in ids:
                delivered += int(deliver_member_email(pk))
        self.stdout.write(f'Discovered {discovered} campaign(s); queued {queued} member email(s); sent/captured {delivered}.')
