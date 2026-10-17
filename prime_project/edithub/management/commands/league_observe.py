from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from edithub.models import EditorApplication
from edithub.league_models import MetricSnapshot
from edithub.league.integration import fetch_verified_video


class Command(BaseCommand):
    help = 'Collect a verified comparison video observation for the pilot/baselines. Awards no points.'

    def add_arguments(self, parser):
        parser.add_argument('--application', type=int, required=True)
        parser.add_argument('--video', required=True)

    def handle(self, *args, **options):
        try:
            application = EditorApplication.objects.get(pk=options['application'])
            data = fetch_verified_video(application, options['video'])
            snapshot = MetricSnapshot.objects.create(
                editor=application.user, platform=data['platform'], video_id=data['video_id'],
                channel_id=data['channel_id'], video_format=data['video_format'], published_at=data['published_at'],
                requested_at=data['requested_at'], completed_at=data['completed_at'], received_at=timezone.now(),
                likes=data['likes'], views=data['views'], status='success', provider=data['provider'], provenance=data.get('provenance', {}),
            )
        except Exception as exc:
            # Do not print provider tokens or credential-file contents in CLI output.
            raise CommandError(f'Observation unavailable ({type(exc).__name__}). Check the approved channel and provider configuration.') from exc
        self.stdout.write(f'Stored comparison observation {snapshot.pk}. No league points awarded.')
