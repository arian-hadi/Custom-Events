from django.db import migrations


def seed_requests(apps, schema_editor):
    Request = apps.get_model('shop', 'FeaturedShopRequest')
    for order, title, icon, description, details in [
        (10, 'Edit Request', 'edit',
         'Your idea, your style. A dedicated place to request a custom edit.',
         'Custom edit options are on the way. Available styles, reference requirements, delivery times, and revision options will be listed here before requests open.'),
        (20, 'Media Request', 'media',
         'Looking for something specific? Explore media made around your request.',
         'Media request options are on the way. Available formats, what you receive, and delivery details will be listed here before requests open.'),
    ]:
        Request.objects.using(schema_editor.connection.alias).create(
            title=title, icon=icon, description=description, details=details,
            sort_order=order, is_active=True, is_placeholder=True,
            button_label='Request on Buy Me a Coffee',
        )


class Migration(migrations.Migration):
    dependencies = [('shop', '0013_featuredshoprequest')]
    # Keep admin-authored content when reversing the seed step.
    operations = [migrations.RunPython(seed_requests, migrations.RunPython.noop)]
