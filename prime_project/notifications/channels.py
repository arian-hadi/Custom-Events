"""Notification channels share the member's master and per-topic preferences."""
from .activity_email import TYPE_FIELDS, preference_enabled, queue_activity_email


class InAppChannel:
    def is_enabled_for_user(self, preferences, notification_type):
        field = TYPE_FIELDS.get(notification_type, '').replace('email_', 'in_app_', 1)
        return bool(preferences.in_app_enabled and (not field or getattr(preferences, field, True)))

    def send(self, notification, preferences):
        return self.is_enabled_for_user(preferences, notification.notification_type)


class EmailChannel:
    """Persist the outbox in the originating transaction; never send inline."""
    def is_enabled_for_user(self, preferences, notification_type):
        return preference_enabled(preferences, notification_type)

    def send(self, notification, preferences):
        return queue_activity_email(notification, preferences)
