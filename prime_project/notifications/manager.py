"""
Notification Manager - Unified interface for creating and sending notifications.
"""
import logging
from .models import Notification, NotificationPreference
from .channels import InAppChannel, EmailChannel

logger = logging.getLogger(__name__)


class NotificationManager:
    """Unified interface for creating and sending notifications"""
    
    def __init__(self):
        """Initialize notification manager with available channels"""
        self.channels = {
            'in_app': InAppChannel(),
            'email': EmailChannel(),  # Will be active in Phase 2
        }
    
    def create_notification(self, user, title, message, notification_type, 
                          related_object=None, send_channels=None):
        """
        Create notification and send via specified channels.
        
        Args:
            user: CustomUser instance
            title: Notification title
            message: Notification message
            notification_type: Type of notification (from Notification.NOTIFICATION_TYPE_CHOICES)
            related_object: Optional related object (e.g., EditorApplication, EditorTitle)
            send_channels: List of channel names to use (e.g., ['in_app', 'email'])
                          If None, uses all enabled channels based on user preferences
        
        Returns:
            Notification instance or None if creation failed
        """
        try:
            # Create notification (saves to DB)
            notification = Notification.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                related_object_type=related_object.__class__.__name__ if related_object else None,
                related_object_id=related_object.id if related_object else None
            )
            
            # Get or create user preferences
            prefs, _ = NotificationPreference.objects.get_or_create(user=user)
            
            # Determine which channels to use
            if send_channels is None:
                # Auto-determine based on user preferences
                send_channels = []
                for channel_name, channel in self.channels.items():
                    if channel.is_enabled_for_user(prefs, notification_type):
                        send_channels.append(channel_name)
            
            # Send via each channel
            for channel_name in send_channels:
                if channel_name in self.channels:
                    try:
                        self.channels[channel_name].send(notification, prefs)
                    except Exception as e:
                        logger.error(
                            f"Failed to send notification {notification.id} "
                            f"via {channel_name} to {user.username}: {str(e)}"
                        )
            
            return notification
            
        except Exception as e:
            logger.error(f"Failed to create notification for {user.username}: {str(e)}")
            return None
    
    def get_unread_count(self, user):
        """Get count of unread notifications for a user"""
        return Notification.objects.filter(user=user, is_read=False).count()
    
    def mark_all_as_read(self, user):
        """Mark all notifications as read for a user"""
        return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


# Global instance
notification_manager = NotificationManager()

