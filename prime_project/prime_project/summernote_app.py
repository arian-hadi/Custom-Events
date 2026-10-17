"""Keep Summernote's attachment IDs aligned with its shipped migrations."""
from django_summernote.apps import DjangoSummernoteConfig


class SummernoteConfig(DjangoSummernoteConfig):
    # The package's initial migration creates an AutoField. Without this
    # override Django inherits our project-wide BigAutoField and proposes an
    # unshipped migration inside site-packages on every clean deployment.
    default_auto_field = 'django.db.models.AutoField'
