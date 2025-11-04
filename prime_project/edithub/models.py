from django.db import models
from accounts.models import CustomUser
from django.utils import timezone


class EditorApplication(models.Model):
    """Model for editor applications to the EditingHub ranking table"""
    
    CHANNEL_TYPE_CHOICES = [
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
    ]
    
    EDITING_AREA_CHOICES = [
        ('transformers', 'Transformers'),
        ('dc', 'DC'),
        ('marvel', 'Marvel'),
        ('anime', 'Anime'),
        ('all', 'All'),
        ('others', 'Others'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='editor_applications'
    )
    
    # Channel information
    channel_link = models.URLField(max_length=500, help_text="YouTube or TikTok channel URL")
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    channel_name = models.CharField(max_length=200, blank=True, help_text="Fetched from channel")
    channel_thumbnail = models.URLField(max_length=500, blank=True, help_text="Channel thumbnail URL")
    follower_count = models.BigIntegerField(default=0, help_text="Follower/subscriber count")
    
    # Application details
    editing_area = models.CharField(max_length=50, choices=EDITING_AREA_CHOICES)
    editing_area_other = models.CharField(max_length=200, blank=True, help_text="If 'others' is selected")
    
    # Verification and consent
    channel_verified = models.BooleanField(default=False, help_text="User confirmed this is their channel")
    data_consent = models.BooleanField(default=False, help_text="User consented to data usage")
    channel_screenshot = models.ImageField(
        upload_to='editinghub_screenshots/', 
        blank=True, 
        null=True,
        help_text="Screenshot of the channel page to verify ownership"
    )
    
    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    reviewed_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        limit_choices_to={'role': 'admin'}
    )
    
    # Ranking position (calculated based on follower count)
    rank_position = models.IntegerField(null=True, blank=True, help_text="Position in ranking table")
    
    # User can request removal
    removal_requested = models.BooleanField(default=False)
    removal_requested_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-follower_count', 'applied_date']
        unique_together = ('user', 'channel_link')  # One application per user per channel
        
    def __str__(self):
        return f"{self.user.username} - {self.channel_name or self.channel_link} ({self.get_status_display()})"
    
    @staticmethod
    def update_rank_positions():
        """Update rank positions for all accepted applications based on follower count"""
        # Get all accepted applications ordered by follower count
        accepted_apps = EditorApplication.objects.filter(
            status='accepted',
            removal_requested=False
        ).order_by('-follower_count', 'applied_date')
        
        for index, app in enumerate(accepted_apps, start=1):
            app.rank_position = index
            app.save(update_fields=['rank_position'])
    
    def update_rank_position(self):
        """Update rank position based on follower count - instance method for backward compatibility"""
        EditorApplication.update_rank_positions()
    
    def save(self, *args, **kwargs):
        """Override save to update rankings when status changes"""
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_obj = EditorApplication.objects.get(pk=self.pk)
                old_status = old_obj.status
            except EditorApplication.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update rankings if status changed to accepted or if this is a new accepted application
        if self.status == 'accepted' and (is_new or old_status != 'accepted'):
            EditorApplication.update_rank_positions()
        elif old_status == 'accepted' and self.status != 'accepted':
            # Recalculate all rankings if an accepted application changed status
            EditorApplication.update_rank_positions()
