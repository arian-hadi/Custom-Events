from django.db import models
from django.utils import timezone
from accounts.models import CustomUser


class Notification(models.Model):
    """Core notification model - stores all notifications"""
    
    NOTIFICATION_TYPE_CHOICES = [
        ('application_approved', 'Application Approved'),
        ('application_disapproved', 'Application Disapproved'),
        ('ranking_updated', 'Ranking Updated'),
        ('edit_of_week_daily', 'Edit of the Week Daily Report'),
        ('title_unlocked', 'Title Unlocked'),
        ('edit_verified', 'Edit Verified'),
        ('edit_rejected', 'Edit Rejected'),
    ]
    
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50, 
        choices=NOTIFICATION_TYPE_CHOICES
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional: link to related object
    related_object_type = models.CharField(max_length=50, blank=True, null=True)
    related_object_id = models.IntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'notification_type']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.title} ({'read' if self.is_read else 'unread'})"
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save(update_fields=['is_read'])


class NotificationPreference(models.Model):
    """User preferences for notification channels"""
    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Channel preferences
    email_enabled = models.BooleanField(
        default=True,
        help_text="Enable email notifications (will be used in Phase 2)"
    )
    in_app_enabled = models.BooleanField(
        default=True,
        help_text="Enable in-app notifications"
    )
    
    # Per-type preferences (optional, for granular control)
    email_application_updates = models.BooleanField(default=True)
    email_ranking_updates = models.BooleanField(default=True)
    email_edit_reports = models.BooleanField(default=True)
    email_achievements = models.BooleanField(default=True)
    
    in_app_application_updates = models.BooleanField(default=True)
    in_app_ranking_updates = models.BooleanField(default=True)
    in_app_edit_reports = models.BooleanField(default=True)
    in_app_achievements = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"
    
    def __str__(self):
        return f"Preferences for {self.user.username}"
