from django.core.management.base import BaseCommand
from django.utils import timezone

from edithub.league_models import CompetitionWeek
from edithub.league import services


class Command(BaseCommand):
    help = 'Activate due rounds and finalize eligible weeks and calendar months. Run from one external scheduler.'

    def handle(self, *args, **options):
        now = timezone.now()
        for week in CompetitionWeek.objects.filter(state='scheduled', start_at__lte=now, cutoff_at__gt=now):
            try:
                services.activate_week(week, now=now)
                self.stdout.write(f'Activated week {week.pk}.')
            except ValueError as exc:
                self.stderr.write(f'Week {week.pk} not activated: {exc}')
        for week in CompetitionWeek.objects.filter(state__in=['live', 'finalizing'], cutoff_at__lte=now):
            try:
                services.finalize_week(week, now=now)
                self.stdout.write(f'Finalized week {week.pk}.')
            except ValueError as exc:
                self.stderr.write(f'Week {week.pk} remains pending: {exc}')
        periods = CompetitionWeek.objects.filter(scoring_date__lt=now.date()).values_list('scoring_date', flat=True)
        for year, month in sorted({(value.year, value.month) for value in periods}):
            if (year, month) >= (now.year, now.month):
                continue
            try:
                services.finalize_month(year, month, now=now)
            except ValueError as exc:
                self.stderr.write(f'Month {year}-{month:02d} remains pending: {exc}')
