from django.db import migrations


def map_legacy_editing_tools(apps, schema_editor):
    EditorApplication = apps.get_model('edithub', 'EditorApplication')
    legacy_values = ['premiere', 'davinci', 'final_cut', 'sony_vegas']
    EditorApplication.objects.filter(editing_tool__in=legacy_values).update(editing_tool='other')


class Migration(migrations.Migration):

    dependencies = [
        ('edithub', '0003_editorapplication_editing_tool'),
    ]

    operations = [
        migrations.RunPython(map_legacy_editing_tools, migrations.RunPython.noop),
    ]

