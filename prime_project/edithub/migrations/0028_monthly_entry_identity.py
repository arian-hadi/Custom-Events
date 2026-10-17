from django.db import migrations, models
from django.db.models import Q


def assign_competition_month(apps, schema_editor):
    Entry = apps.get_model('edithub', 'CompetitionEntry')
    Week = apps.get_model('edithub', 'CompetitionWeek')
    database = schema_editor.connection.alias
    # Historical rows acquire a lookup scope only; results, snapshots and
    # awards are deliberately untouched, including withdrawn entries.
    for week_id, friday in Week.objects.using(database).values_list('pk', 'scoring_date').iterator():
        Entry.objects.using(database).filter(week_id=week_id).update(competition_month=friday.replace(day=1))


class Migration(migrations.Migration):
    dependencies = [('edithub', '0027_leaguesettings_and_more')]

    operations = [
        migrations.AddField(
            model_name='competitionentry', name='competition_month',
            field=models.DateField(null=True, editable=False, help_text="First day of the month containing the competition's Friday cutoff."),
        ),
        migrations.RunPython(assign_competition_month, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='competitionentry', name='competition_month',
            field=models.DateField(editable=False, help_text="First day of the month containing the competition's Friday cutoff."),
        ),
        migrations.RemoveConstraint(model_name='competitionentry', name='league_one_canonical_video'),
        migrations.RemoveConstraint(model_name='competitionentry', name='league_one_underlying_edit'),
        migrations.AddConstraint(
            model_name='competitionentry', constraint=models.UniqueConstraint(
                fields=['competition_month', 'platform', 'video_id'], condition=~Q(state='withdrawn'), name='league_video_once_per_month'),
        ),
        migrations.AddConstraint(
            model_name='competitionentry', constraint=models.UniqueConstraint(
                fields=['competition_month', 'content_key'], condition=~Q(state='withdrawn'), name='league_edit_once_per_month'),
        ),
    ]
