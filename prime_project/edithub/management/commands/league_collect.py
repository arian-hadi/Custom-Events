from edithub.league.automation import league_enabled
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from edithub.league_models import CompetitionEntry
from edithub.league.integration import fetch_verified_video
from edithub.league.services import record_snapshot


class Command(BaseCommand):
    help = 'Collect provider totals for currently open V2 rounds. Never fetch closing totals after cutoff.'

    def add_arguments(self, parser):
        parser.add_argument('--week', type=int)

    def handle(self, *args, **options):
        if not league_enabled():
            self.stdout.write('League collection is disabled.')
            return
        now = timezone.now()
        entries = CompetitionEntry.objects.filter(
            week__state='live', week__start_at__lte=now, week__cutoff_at__gt=now,
            state__in=['active', 'data_pending'],
        )
        if options.get('week'):
            entries = entries.filter(week_id=options['week'])
        count = errors = skipped = 0
        week_ids = set(entries.values_list('week_id', flat=True))
        for entry_id in entries.values_list('pk', flat=True).iterator():
            # A database lock prevents separate scheduler processes from polling
            # the same entry at once. PostgreSQL skips another worker's locked row.
            with transaction.atomic():
                entry = CompetitionEntry.objects.select_for_update(skip_locked=True, of=('self',)).select_related(
                    'approved_application', 'week__scoring_version').filter(pk=entry_id).first()
                started = timezone.now()
                if (entry is None or entry.state not in {'active', 'data_pending'} or entry.week.state != 'live'
                        or not entry.week.start_at <= started < entry.week.cutoff_at):
                    skipped += 1
                    continue
                window = entry.week.scoring_version.config.get('cutoff_max_age_seconds', 900)
                interval = 300 if started >= entry.week.cutoff_at - timedelta(seconds=window) else 3600
                last = entry.snapshots.order_by('-completed_at', '-pk').first()
                # Failed attempts are also paced to avoid exhausting a provider's
                # quota on every scheduler tick. Missing counters remain null.
                if last and last.completed_at > started - timedelta(seconds=interval):
                    skipped += 1
                    continue
                try:
                    if not entry.approved_application:
                        raise ValueError('Missing approved channel association.')
                    data = fetch_verified_video(entry.approved_application, entry.canonical_url)
                    if data.get('video_format') != entry.video_format or data.get('published_at') != entry.published_at:
                        raise ValueError('Provider metadata no longer matches the locked entry.')
                    if data['completed_at'] >= entry.week.cutoff_at:
                        data['provenance'] = {**data.get('provenance', {}), 'after_cutoff': True}
                    record_snapshot(entry, data)
                    count += 1
                except Exception as exc:
                    errors += 1
                    record_snapshot(entry, {
                        'likes': None, 'views': None, 'requested_at': started,
                        'completed_at': timezone.now(), 'status': 'error', 'provider': entry.platform,
                        'provenance': {'failure_type': type(exc).__name__},
                    })
                    self.stderr.write(f'Entry {entry.pk}: collection unavailable ({type(exc).__name__}).')
        from notifications.league_activity import notify_provisional_leader
        for week_id in sorted(week_ids):
            notify_provisional_leader(week_id)
        self.stdout.write(f'Collected {count} observation(s); {errors} unavailable; {skipped} not due. Missing metrics were not replaced with zero.')
