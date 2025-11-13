from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('edithub', '0004_update_editing_tool_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='editorapplication',
            name='rank_position_last_week',
            field=models.IntegerField(blank=True, null=True, help_text='Last week\'s position for trend arrows'),
        ),
        migrations.AddField(
            model_name='editorapplication',
            name='rank_snapshot_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When last weekly rank snapshot was taken'),
        ),
    ]


