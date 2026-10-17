from datetime import date, datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError
from edithub.league_models import ScoringVersion
from edithub.league.services import ensure_week


class Command(BaseCommand):
    help = 'Create additive V2 rounds using a named scoring version. Does not activate scoring.'

    def add_arguments(self, parser):
        parser.add_argument('--version', required=True)
        parser.add_argument('--start', required=True, help='Monday date, YYYY-MM-DD, in UTC.')
        parser.add_argument('--weeks', type=int, default=8)

    def handle(self, *args, **options):
        try:
            version = ScoringVersion.objects.get(name=options['version'])
            start = datetime.combine(date.fromisoformat(options['start']), datetime.min.time(), tzinfo=timezone.utc)
            if not 1 <= options['weeks'] <= 104:
                raise ValueError('Use 1 to 104 weeks.')
            for offset in range(options['weeks']):
                ensure_week(start + timedelta(weeks=offset), version)
        except (ValueError, ScoringVersion.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Prepared {options["weeks"]} V2 round(s); no scoring jobs were started.')
