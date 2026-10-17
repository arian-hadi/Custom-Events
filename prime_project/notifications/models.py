from django.db import models
from django.utils import timezone
from accounts.models import CustomUser
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
import re


ADMIN_ALERT_TYPES = [
    ('youtube_blog_video', 'New YouTube videos for the blog'),
    ('editor_application', 'New editor applications'),
    ('editor_removal', 'Editor removal requests'),
    ('edit_submission', 'New edit submissions'),
    ('edit_report', 'Edit moderation reports'),
    ('event_application', 'New event applications'),
]


def parse_admin_recipients(value):
    """Validate explicit administrator recipients; never use applicant addresses."""
    values = re.split(r'[,;\s]+', value.strip()) if isinstance(value, str) else value
    result = []
    for address in values or []:
        if not address:
            continue
        validate_email(address)
        address = address.strip().lower()
        if address not in result:
            result.append(address)
    if len(result) > 20:
        raise ValidationError('Use at most 20 administrator email addresses.')
    return result


class AdminEmailSettings(models.Model):
    """Administrator operational alerts, independent of member subscriptions."""
    enabled = models.BooleanField(default=True)
    recipients = models.TextField(blank=True, help_text=(
        'One email per line (commas also work). Blank uses ADMIN_NOTIFICATION_RECIPIENTS, '
        'then active superuser email addresses. These recipients receive application details.'
    ))
    editor_application = models.BooleanField(default=True, verbose_name='New editor applications')
    editor_removal = models.BooleanField(default=True, verbose_name='Editor removal requests')
    edit_submission = models.BooleanField(default=True, verbose_name='New edit submissions')
    edit_report = models.BooleanField(default=True, verbose_name='Edit moderation reports')
    event_application = models.BooleanField(default=True, verbose_name='New event applications')
    youtube_blog_video = models.BooleanField(default=True, verbose_name='New YouTube videos for the blog')
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        try:
            self.recipients = '\n'.join(parse_admin_recipients(self.recipients))
        except ValidationError as exc:
            raise ValidationError({'recipients': exc.messages}) from exc

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return 'Admin email alerts'

    class Meta:
        verbose_name = 'Admin email settings'
        verbose_name_plural = 'Admin email settings'


class AdminEmailDelivery(models.Model):
    """Durable, deduplicated delivery record; a failed email never rejects a submission."""
    kind = models.CharField(max_length=30, choices=ADMIN_ALERT_TYPES)
    object_label = models.CharField(max_length=100)
    object_id = models.PositiveBigIntegerField()
    recipient = models.EmailField()
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'),
        ('captured', 'Captured locally'), ('failed', 'Failed'), ('cancelled', 'Cancelled'),
    ])
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(
            fields=['kind', 'object_label', 'object_id', 'recipient'], name='unique_admin_alert_recipient',
        )]
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='admin_alert_delivery_due')]
        verbose_name = 'Admin email delivery'
        verbose_name_plural = 'Admin email deliveries'

    def __str__(self):
        return f'{self.get_kind_display()} #{self.object_id} — {self.get_status_display()}'


class Notification(models.Model):
    """Core notification model - stores all notifications"""
    
    NOTIFICATION_TYPE_CHOICES = [
        ('community_announcement', 'Community Announcement'),
        ('application_approved', 'Application Approved'),
        ('application_disapproved', 'Application Disapproved'),
        ('ranking_updated', 'Ranking Updated'),
        ('edit_of_week_daily', 'Edit of the Week Daily Report'),
        ('title_unlocked', 'Title Unlocked'),
        ('edit_verified', 'Edit Verified'),
        ('edit_rejected', 'Edit Rejected'),
        ('league_result', 'League Result'),
        ('league_ranking', 'League Standing'),
        ('league_award', 'League Achievement'),
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
    event_key = models.CharField(max_length=180, unique=True, null=True, blank=True, editable=False)
    
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
        help_text="Master switch for optional member emails; account security and order receipts are separate."
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
    # Marketing requires explicit opt-in; existing members are never enrolled by migration.
    email_newsletter = models.BooleanField(default=False)
    email_blog_updates = models.BooleanField(default=False)
    email_shop_updates = models.BooleanField(default=False)
    
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


CAMPAIGN_TOPICS = [('newsletter', 'Newsletter'), ('blog_updates', 'Blog updates'), ('shop_updates', 'Shop updates')]


class MemberEmailSettings(models.Model):
    """Automation must be explicitly enabled, and starts at that enable time."""
    automatic_blog = models.BooleanField(default=False)
    automatic_shop = models.BooleanField(default=False)
    blog_enabled_since = models.DateTimeField(null=True, blank=True, editable=False)
    shop_enabled_since = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        old = type(self).objects.filter(pk=1).first()
        for topic in ('blog', 'shop'):
            enabled = getattr(self, f'automatic_{topic}')
            was_enabled = old and getattr(old, f'automatic_{topic}')
            field = f'{topic}_enabled_since'
            setattr(self, field, getattr(old, field) if enabled and was_enabled else timezone.now() if enabled else None)
        self.full_clean()
        # Include the activation cutoffs even when a caller uses update_fields.
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'blog_enabled_since', 'shop_enabled_since'}
        return super().save(*args, **kwargs)

    def __str__(self):
        return 'Member email automation'

    class Meta:
        verbose_name = 'Member email automation settings'
        verbose_name_plural = 'Member email automation settings'


class MemberEmailCampaign(models.Model):
    topic = models.CharField(max_length=20, choices=CAMPAIGN_TOPICS, default='newsletter')
    subject = models.CharField(max_length=180)
    body = models.TextField(help_text='Plain text. The sender address and unsubscribe links are appended automatically.')
    status = models.CharField(max_length=12, default='draft', choices=[
        ('draft', 'Draft'), ('scheduled', 'Scheduled'), ('queued', 'Queued'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])
    scheduled_at = models.DateTimeField(default=timezone.now)
    source_key = models.CharField(max_length=100, unique=True, null=True, blank=True, editable=False)
    created_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, editable=False)
    queued_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if any(character in self.subject for character in '\r\n'):
            raise ValidationError({'subject': 'Email subjects must be a single line.'})
        if not self.body.strip() or len(self.body) > 50000:
            raise ValidationError({'body': 'Use between 1 and 50,000 characters.'})
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).first()
            if old and (old.queued_at or old.status == 'cancelled'):
                immutable = ('subject', 'body', 'topic', 'scheduled_at', 'source_key', 'queued_at')
                if any(getattr(old, field) != getattr(self, field) for field in immutable):
                    raise ValidationError('Queued campaign content is frozen. Create a new draft for changes.')
                if self.status not in {old.status, 'cancelled'}:
                    raise ValidationError('A queued campaign cannot be rescheduled or reopened.')

    def save(self, *args, **kwargs):
        from django.db import transaction
        with transaction.atomic():
            # Serialize admin edits with queue_campaign's freeze transition.
            if self.pk:
                type(self).objects.select_for_update().filter(pk=self.pk).first()
            # Let the unique database constraint arbitrate concurrent automatic
            # discoveries so get_or_create can handle the IntegrityError safely.
            self.full_clean(validate_unique=False)
            return super().save(*args, **kwargs)

    def __str__(self):
        return self.subject

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'scheduled_at'], name='member_campaign_due')]


class MemberEmailDelivery(models.Model):
    campaign = models.ForeignKey(MemberEmailCampaign, on_delete=models.PROTECT, related_name='deliveries')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='campaign_deliveries')
    recipient = models.EmailField()
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'),
        ('captured', 'Captured locally'), ('failed', 'Failed'), ('cancelled', 'Cancelled'),
    ])
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['campaign', 'user'], name='unique_member_campaign_user')]
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='member_email_delivery_due')]

    def __str__(self):
        return f'{self.campaign_id}: {self.get_status_display()}'


class MemberActivityDelivery(models.Model):
    """One durable optional email per notification, with content frozen at queue time."""
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='email_delivery')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='activity_email_deliveries')
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    target_path = models.CharField(max_length=300, default='/notifications')
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'),
        ('captured', 'Captured locally'), ('failed', 'Failed'), ('cancelled', 'Cancelled'),
    ])
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='member_activity_email_due')]
        verbose_name = 'Member activity email delivery'
        verbose_name_plural = 'Member activity email deliveries'

    def __str__(self):
        return f'{self.notification_id}: {self.get_status_display()}'


class LeagueNotificationEvent(models.Model):
    """Written inside the league transaction; processed only after results commit."""
    event_key = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=12, choices=[('weekly', 'Weekly revision'), ('monthly', 'Monthly award'), ('season', 'Season award')])
    object_id = models.PositiveBigIntegerField()
    email_eligible = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        indexes = [models.Index(fields=['processed_at', 'created_at'], name='league_notification_pending')]
