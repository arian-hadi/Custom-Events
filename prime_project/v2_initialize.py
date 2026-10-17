"""Apply existing migrations (including their data steps), then collect static."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prime_project.settings')

import django
from django.core.management import call_command

django.setup()
call_command('migrate', interactive=False)
# The live gateway serves Django source static files. Only the built preview
# needs the collected/compressed snapshot, which is expensive on every restart.
if os.environ.get('V2_COLLECT_STATIC', 'True').lower() not in {'false', '0', 'no'}:
    call_command('collectstatic', interactive=False)
