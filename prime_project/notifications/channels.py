"""
Notification channel handlers.
Each channel handles delivery of notifications through a specific medium.
"""
import logging

logger = logging.getLogger(__name__)


class NotificationChannel:
    """Base class for notification channels"""
    
    def send(self, notification, user_preferences):
        """
        Send notification through this channel.
        
        Args:
            notification: Notification instance
            user_preferences: NotificationPreference instance
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        raise NotImplementedError("Subclasses must implement send()")
    
    def is_enabled_for_user(self, user_preferences, notification_type):
        """
        Check if this channel is enabled for the user and notification type.
        
        Args:
            user_preferences: NotificationPreference instance
            notification_type: Type of notification
            
        Returns:
            bool: True if enabled, False otherwise
        """
        raise NotImplementedError("Subclasses must implement is_enabled_for_user()")


class InAppChannel(NotificationChannel):
    """In-app notifications - stores in database"""
    
    def send(self, notification, user_preferences):
        """
        In-app notifications are already saved in the database.
        This method just verifies the user has in-app notifications enabled.
        """
        if not self.is_enabled_for_user(user_preferences, notification.notification_type):
            return False
        
        # Notification is already saved in DB, just return success
        logger.info(f"In-app notification sent: {notification.id} to {notification.user.username}")
        return True
    
    def is_enabled_for_user(self, user_preferences, notification_type):
        """Check if in-app notifications are enabled for this notification type"""
        if not user_preferences.in_app_enabled:
            return False
        
        # Check per-type preferences
        type_mapping = {
            'application_approved': 'in_app_application_updates',
            'application_disapproved': 'in_app_application_updates',
            'ranking_updated': 'in_app_ranking_updates',
            'edit_of_week_daily': 'in_app_edit_reports',
            'title_unlocked': 'in_app_achievements',
            'edit_verified': 'in_app_edit_reports',
            'edit_rejected': 'in_app_edit_reports',
        }
        
        preference_field = type_mapping.get(notification_type, None)
        if preference_field:
            return getattr(user_preferences, preference_field, True)
        
        return True


class EmailChannel(NotificationChannel):
    """
    Email notifications - to be implemented in Phase 2.
    This is a placeholder that will use the existing email system.
    """
    
    def send(self, notification, user_preferences):
        """
        Send notification via email.
        This will be implemented in Phase 2.
        """
        if not self.is_enabled_for_user(user_preferences, notification.notification_type):
            return False
        
        # TODO: Implement email sending in Phase 2
        # from accounts.utils import send_normal_email
        # send_normal_email({
        #     'email_subject': notification.title,
        #     'email_body': notification.message,
        #     'to_email': notification.user.email
        # })
        
        logger.info(f"Email notification would be sent: {notification.id} to {notification.user.email}")
        return False  # Return False for now since not implemented
    
    def is_enabled_for_user(self, user_preferences, notification_type):
        """Check if email notifications are enabled for this notification type"""
        if not user_preferences.email_enabled:
            return False
        
        # Check per-type preferences
        type_mapping = {
            'application_approved': 'email_application_updates',
            'application_disapproved': 'email_application_updates',
            'ranking_updated': 'email_ranking_updates',
            'edit_of_week_daily': 'email_edit_reports',
            'title_unlocked': 'email_achievements',
            'edit_verified': 'email_edit_reports',
            'edit_rejected': 'email_edit_reports',
        }
        
        preference_field = type_mapping.get(notification_type, None)
        if preference_field:
            return getattr(user_preferences, preference_field, True)
        
        return True

