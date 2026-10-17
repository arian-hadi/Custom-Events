"""One current editor channel per member; existing records remain historical."""

from .models import EditorApplication


ACTIVE_APPLICATION_STATUSES = ('pending', 'accepted')
SINGLE_CHANNEL_MESSAGE = 'You can have one active editor application: YouTube or TikTok. Open your existing application to continue.'


def active_application(user, *, exclude_id=None):
    return (EditorApplication.objects.filter(user=user, status__in=ACTIVE_APPLICATION_STATUSES,
                                             removal_requested=False)
            .exclude(pk=exclude_id).order_by('-applied_date', '-pk').first())


def activates_application(instance, user, status, removal_requested):
    """Grandfather current records, while preventing new or reactivated duplicates."""
    if status not in ACTIVE_APPLICATION_STATUSES or removal_requested:
        return False
    if not instance.pk:
        return True
    return not EditorApplication.objects.filter(
        pk=instance.pk, user=user, status__in=ACTIVE_APPLICATION_STATUSES,
        removal_requested=False,
    ).exists()
