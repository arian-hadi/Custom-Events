from urllib.parse import urlencode

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from edithub.league.preview import STATES, issue_token, preview_enabled


class Command(BaseCommand):
    help = 'Print a two-hour local preview link with sample league data. Does not start or change real competitions.'

    def add_arguments(self, parser):
        parser.add_argument('--state', choices=STATES, default='live', help='Initial view: live, frozen, or pending.')

    def handle(self, *args, **options):
        if not preview_enabled():
            raise CommandError('Preview requires DEBUG=True and a localhost V2_FRONTEND_URL. No competition was changed.')
        query = urlencode({'token': issue_token(), 'state': options['state']})
        self.stdout.write('Local sample preview only. Real entries, schedules and points are unchanged. Link expires in two hours.')
        self.stdout.write(f"{settings.V2_FRONTEND_URL.rstrip('/')}/editing-hub/preview?{query}")
