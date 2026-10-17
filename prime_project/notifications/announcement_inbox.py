"""Materialize public announcements in each member's existing private inbox."""
from django.db.models import Q

from announcements.models import Announcement
from .models import Notification, NotificationPreference


def member_notifications(user):
    active = Announcement.objects.filter(is_active=True)
    enabled = not NotificationPreference.objects.filter(user=user, in_app_enabled=False).exists()
    if enabled:
        for item in active.only('id', 'title', 'created_at').iterator():
            key = f'announcement:{item.pk}:member:{user.pk}'
            notice, created = Notification.objects.get_or_create(event_key=key, defaults={
                'user': user, 'title': item.title, 'message': '',
                'notification_type': 'community_announcement',
                'related_object_type': 'Announcement', 'related_object_id': item.pk,
            })
            if created:
                Notification.objects.filter(pk=notice.pk).update(created_at=item.created_at)
            elif notice.title != item.title:
                Notification.objects.filter(pk=notice.pk).update(title=item.title)
    queryset = Notification.objects.filter(user=user)
    if not enabled:
        return queryset.exclude(notification_type='community_announcement')
    return queryset.filter(~Q(notification_type='community_announcement') |
                           Q(related_object_id__in=active.values('pk')))
