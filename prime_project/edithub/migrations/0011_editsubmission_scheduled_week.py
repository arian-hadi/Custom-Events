from django.db import migrations, models
from datetime import timedelta


def populate_scheduled_week(apps, schema_editor):
    EditSubmission = apps.get_model('edithub', 'EditSubmission')
    for submission in EditSubmission.objects.all().only('id', 'submitted_date'):
        if submission.submitted_date and not submission.scheduled_week:
            week_start = submission.submitted_date.date() - timedelta(days=submission.submitted_date.weekday())
            EditSubmission.objects.filter(pk=submission.pk).update(scheduled_week=week_start)


class Migration(migrations.Migration):

    dependencies = [
        ('edithub', '0010_add_direct_video_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='editsubmission',
            name='scheduled_week',
            field=models.DateField(blank=True, help_text='Monday (UTC) of the competition week this edit participates in', null=True),
        ),
        migrations.RunPython(populate_scheduled_week, migrations.RunPython.noop),
    ]

