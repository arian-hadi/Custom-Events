"""Collect actual comparison observations before future baselines are frozen."""

from edithub.league.automation import league_enabled
from datetime import timedelta
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from edithub.league.integration import approved_channel_context, fetch_verified_video_id
from edithub.league.providers import list_channel_video_ids
from edithub.league.services import record_comparison_snapshot
from edithub.league_models import CompetitionEntry, CompetitionWeek, LeagueHistorySync
from edithub.models import EditorApplication


class Command(BaseCommand):
    help = 'Collect bounded hourly comparison history for approved league entrants. Never backdates observations or changes frozen baselines.'

    def add_arguments(self, parser):
        parser.add_argument('--application', type=int)
        parser.add_argument('--limit', type=int, default=8, help='Maximum video fetches per channel (1–20).')
        parser.add_argument('--channels', type=int, default=4, help='Maximum channels per cycle (1–25).')
        parser.add_argument('--budget-seconds', type=int, default=30, help='Stop starting provider requests after this cycle budget (1–120 seconds).')

    def handle(self, *args, **options):
        if not league_enabled():
            self.stdout.write('League history collection is disabled.')
            return
        if not (1 <= options['limit'] <= 20 and 1 <= options['channels'] <= 25 and 1 <= options['budget_seconds'] <= 120):
            raise CommandError('Use 1–20 videos, 1–25 channels and a 1–120 second budget.')
        now = timezone.now()
        # Closing observations are time-critical. Leave the scheduler free to
        # poll entries throughout the final half hour of an open round.
        if CompetitionWeek.objects.filter(state='live', cutoff_at__gt=now, cutoff_at__lte=now + timedelta(minutes=30)).exists():
            self.stdout.write('Comparison history paused while closing metrics are collected.')
            return
        open_entries = CompetitionEntry.objects.filter(
            Q(state='queued', week__state='scheduled', week__start_at__gt=now)
            | Q(state__in=['active', 'data_pending'], week__state='live', week__cutoff_at__gt=now)
        ).exclude(approved_application_id=None).filter(
            week__scoring_version__config__mapping_policy__in=['round_cohort_v1', 'linear_knots_clamped_v1'])
        apps = EditorApplication.objects.filter(
            pk__in=open_entries.values('approved_application_id'), status='accepted', channel_verified=True,
            removal_requested=False, user__is_active=True,
        ).filter(Q(league_history_sync__last_started_at__isnull=True)
                 | Q(league_history_sync__last_started_at__lte=now - timedelta(hours=1)))
        if options.get('application'):
            apps = apps.filter(pk=options['application'])
        application_ids = list(apps.order_by(F('league_history_sync__last_started_at').asc(nulls_first=True), 'pk').values_list('pk', flat=True)[:options['channels']])
        deadline = time.monotonic() + options['budget_seconds']
        processed = stored = failures = 0
        for application_id in application_ids:
            if time.monotonic() >= deadline:
                break
            # Hold the existing application row so two scheduler processes cannot
            # both create sync state or spend this channel's provider quota.
            with transaction.atomic():
                application = EditorApplication.objects.select_for_update(skip_locked=True, of=('self',)).select_related('user').filter(
                    pk=application_id, status='accepted', channel_verified=True, removal_requested=False, user__is_active=True,
                ).first()
                if application is None:
                    continue
                sync, _ = LeagueHistorySync.objects.get_or_create(application=application)
                started = timezone.now()
                if sync.last_started_at and sync.last_started_at > started - timedelta(hours=1):
                    continue
                sync.last_started_at, sync.status = started, 'running'
                sync.observations = sync.failures = 0
                sync.error_code = ''
                sync.save()
                processed += 1
                try:
                    context = approved_channel_context(application)
                    platform, credential, channel_id, _ = context
                    supported_formats = set()
                    for config in open_entries.filter(approved_application=application).values_list('week__scoring_version__config', flat=True):
                        if isinstance(config, dict) and isinstance(config.get('supported_formats'), list):
                            supported_formats.update(value for value in config['supported_formats'] if isinstance(value, str))
                    if not sync.pending_video_ids:
                        batch = list_channel_video_ids(platform, channel_id, credential, limit=20, cursor=sync.next_cursor)
                        sync.pending_video_ids = batch['video_ids']
                        sync.next_cursor = batch['cursor']
                    # Current competition videos are collected by league_collect;
                    # they cannot also be comparison samples for themselves.
                    excluded = set(CompetitionEntry.objects.filter(
                        editor=application.user, platform=platform,
                    ).filter(Q(state='disqualified') | Q(week__state__in=['scheduled', 'live', 'finalizing'])).exclude(
                        state='withdrawn').values_list('video_id', flat=True))
                    sync.pending_video_ids = [video_id for video_id in sync.pending_video_ids if video_id not in excluded]
                    candidates = sync.pending_video_ids[:options['limit']]
                    for video_id in candidates:
                        if time.monotonic() >= deadline:
                            sync.error_code = 'cycle_budget_reached'
                            break
                        try:
                            data = fetch_verified_video_id(application, video_id, context=context)
                            if f"{platform}:{data.get('video_format')}" not in supported_formats:
                                raise ValueError('Format is outside the configured competition scope.')
                            data['provenance'] = {**data.get('provenance', {}),
                                'collection': 'league_comparison_history', 'application_id': application.pk}
                            # A failed insert must not poison the channel's outer
                            # transaction or prevent its retry state being saved.
                            with transaction.atomic():
                                record_comparison_snapshot(application.user, data)
                            sync.observations += 1
                        except Exception as exc:
                            sync.failures += 1
                            # Never persist exception text, API URLs or credentials.
                            sync.error_code = type(exc).__name__[:64]
                        # A failed candidate is retried on the next discovery
                        # pass, rather than starving every older video behind it.
                        sync.pending_video_ids.remove(video_id)
                except Exception as exc:
                    sync.failures += 1
                    sync.error_code = type(exc).__name__[:64]
                sync.last_completed_at = timezone.now()
                sync.status = ('partial' if sync.observations else 'unavailable') if sync.error_code else 'success'
                sync.save()
                stored += sync.observations
                failures += sync.failures
        self.stdout.write(f'Comparison history: {processed} channel(s), {stored} observation(s), {failures} unavailable. Frozen baselines unchanged.')
