"""Queue operational alerts at committed submission lifecycle boundaries.

The outbox owns delivery, commit handling and deduplication. These receivers only
decide whether a persisted record has just become ready for administrator review.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from edithub.models import EditReport, EditSubmission, EditorApplication
from events.models import EventApplication

from .admin_email import queue_admin_alert


TRACKED_FIELDS = {
    EditorApplication: ("channel_verified", "removal_requested", "status"),
    EditSubmission: ("status",),
}


@receiver(pre_save, sender=EditorApplication, dispatch_uid="admin_alert_editor_previous")
@receiver(pre_save, sender=EditSubmission, dispatch_uid="admin_alert_edit_previous")
def remember_previous_state(sender, instance, raw=False, using="default", update_fields=None, **kwargs):
    fields = TRACKED_FIELDS[sender]
    instance._admin_alert_track_transition = not raw and (
        update_fields is None or bool(set(fields).intersection(update_fields))
    )
    instance._admin_alert_previous_state = None
    if instance._admin_alert_track_transition and instance.pk:
        instance._admin_alert_previous_state = sender.objects.using(using).filter(pk=instance.pk).values(*fields).first()


def persisted_transition(sender, instance, using):
    """Do not treat unsaved attributes excluded by update_fields as transitions."""
    if not getattr(instance, "_admin_alert_track_transition", False):
        return None, None
    previous = getattr(instance, "_admin_alert_previous_state", None) or {}
    current = sender.objects.using(using).filter(pk=instance.pk).values(*TRACKED_FIELDS[sender]).first()
    return previous, current


@receiver(post_save, sender=EditorApplication, dispatch_uid="admin_alert_editor_ready")
def editor_application_ready(sender, instance, created, raw=False, using="default", **kwargs):
    if raw:
        return
    previous, current = persisted_transition(sender, instance, using)
    if current is None:
        return
    if (
        current["channel_verified"] and not previous.get("channel_verified", False)
        and current["status"] == "pending" and not current["removal_requested"]
    ):
        queue_admin_alert("editor_application", instance)
    if not created and current["removal_requested"] and not previous.get("removal_requested", False):
        queue_admin_alert("editor_removal", instance)


@receiver(post_save, sender=EditSubmission, dispatch_uid="admin_alert_edit_ready")
def edit_submission_ready(sender, instance, created, raw=False, using="default", **kwargs):
    if raw:
        return
    previous, current = persisted_transition(sender, instance, using)
    # Both legacy confirmation paths persist status='verified'. One assigns a
    # transient channel_verified attribute, which is not an EditSubmission field.
    if current and current["status"] == "verified" and previous.get("status") != "verified":
        queue_admin_alert("edit_submission", instance)


@receiver(post_save, sender=EditReport, dispatch_uid="admin_alert_new_edit_report")
def edit_report_created(sender, instance, created, raw=False, **kwargs):
    if not raw and created and instance.is_active and not instance.is_resolved:
        queue_admin_alert("edit_report", instance)


@receiver(post_save, sender=EventApplication, dispatch_uid="admin_alert_new_event_application")
def event_application_created(sender, instance, created, raw=False, **kwargs):
    if not raw and created and instance.status == "pending":
        # Both public application entry points wrap the application and dynamic
        # answers in one atomic block, so outbox delivery sees every response.
        queue_admin_alert("event_application", instance)
