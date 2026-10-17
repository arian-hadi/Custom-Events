from django.core.management.base import BaseCommand
from edithub.league.automation import prepare_rounds
from edithub.league_models import LeagueSettings


class Command(BaseCommand):
    help = 'Maintain the automatic league calendar. --enable opens it using the documented starter rules.'

    def add_arguments(self, parser):
        parser.add_argument('--enable', action='store_true')

    def handle(self, *args, **options):
        if options['enable']:
            configuration, _ = LeagueSettings.objects.get_or_create(pk=1)
            configuration.enabled = True
            configuration.save()
        weeks = prepare_rounds()
        self.stdout.write(f'{len(weeks)} future rounds ready. Existing rounds and results were preserved.')
