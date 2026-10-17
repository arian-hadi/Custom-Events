"""Create notifications and a durable optional email in one transaction."""
from django.db import transaction
from .models import Notification, NotificationPreference
from .channels import InAppChannel, EmailChannel


class NotificationManager:
    def __init__(self):
        self.channels = {'in_app': InAppChannel(), 'email': EmailChannel()}

    def create_notification(self, user, title, message, notification_type,
                            related_object=None, send_channels=None, event_key=None):
        from .activity_email import is_v2
        if is_v2() and notification_type in {'ranking_updated', 'edit_of_week_daily'}:
            return None
        with transaction.atomic():
            values = dict(user=user, title=title, message=message, notification_type=notification_type,
                          related_object_type=type(related_object).__name__ if related_object else None,
                          related_object_id=related_object.pk if related_object else None)
            if event_key:
                notification, created = Notification.objects.get_or_create(event_key=event_key, defaults=values)
                if not created:
                    return notification
            else:
                notification = Notification.objects.create(**values)
            preferences, _ = NotificationPreference.objects.get_or_create(user=user)
            for name, channel in self.channels.items():
                if send_channels is None or name in send_channels:
                    channel.send(notification, preferences)
            return notification

    def get_unread_count(self, user):
        return Notification.objects.filter(user=user, is_read=False).count()

    def mark_all_as_read(self, user):
        return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


notification_manager = NotificationManager()
