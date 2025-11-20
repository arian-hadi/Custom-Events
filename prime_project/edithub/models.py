from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import CustomUser


class EditorApplication(models.Model):
    """Model for editor applications to the EditingHub ranking table"""
    
    CHANNEL_TYPE_CHOICES = [
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
    ]
    
    EDITING_TOOL_CHOICES = [
        ('after_effects', 'After Effects'),
        ('alight_motion', 'Alight Motion'),
        ('capcut', 'CapCut'),
        ('other', 'Other')
    ]

    EDITING_TOOL_SVG_MAP = {
        'after_effects': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 240 234" xmlns="http://www.w3.org/2000/svg">
    <title>After Effects</title>
    <style type="text/css">.st0{fill:#00005B;}.st1{fill:#9999FF;}</style>
    <g>
        <path class="st0" d="M42.5,0h155C221,0,240,19,240,42.5v149c0,23.5-19,42.5-42.5,42.5h-155C19,234,0,215,0,191.5v-149C0,19,19,0,42.5,0z"/>
        <path class="st1" d="M96.4,140H59.2l-7.6,23.6c-0.2,0.9-1,1.5-1.9,1.4H31c-1.1,0-1.4-0.6-1.1-1.8l32.2-92.3c0.3-1,0.6-1.9,1-3.1c0.4-2.1,0.6-4.3,0.6-6.5c-0.1-0.5,0.3-1,0.8-1.1h25.9c0.7,0,1.2,0.3,1.3,0.8l36.5,102c0.3,1.1,0,1.6-1,1.6h-20.9c-0.7,0.1-1.4-0.4-1.6-1.1L96.4,140z M65,120.1h25.4c-0.6-2.1-1.4-4.6-2.3-7.2c-0.9-2.7-1.8-5.6-2.7-8.6c-1-3.1-1.9-6.1-2.9-9.2s-1.9-6-2.7-8.9c-0.8-2.8-1.5-5.4-2.2-7.8h-0.2c-0.9,4.3-2,8.6-3.4,12.9c-1.5,4.8-3,9.8-4.6,14.8C68.1,111.2,66.5,115.8,65,120.1z"/>
        <path class="st1" d="M187,131h-31.7c0.4,3.1,1.4,6.2,3.1,8.9c1.8,2.7,4.3,4.8,7.3,6c4,1.7,8.4,2.6,12.8,2.5c3.5-0.1,7-0.4,10.4-1.1c3.1-0.4,6.1-1.2,8.9-2.3c0.5-0.4,0.8-0.2,0.8,0.8v15.3c0,0.4-0.1,0.8-0.2,1.2c-0.2,0.3-0.4,0.5-0.7,0.7c-3.2,1.4-6.5,2.4-10,3c-4.7,0.9-9.4,1.3-14.2,1.2c-7.6,0-14-1.2-19.2-3.5c-4.9-2.1-9.2-5.4-12.6-9.5c-3.2-3.9-5.5-8.3-6.9-13.1c-1.4-4.7-2.1-9.6-2.1-14.6c0-5.4,0.8-10.7,2.5-15.9c1.6-5,4.1-9.6,7.5-13.7c3.3-4,7.4-7.2,12.1-9.5s10.3-3.1,16.7-3.1c5.3-0.1,10.6,0.9,15.5,3.1c4.1,1.8,7.7,4.5,10.5,8c2.6,3.4,4.7,7.2,6,11.4c1.3,4,1.9,8.1,1.9,12.2c0,2.4-0.1,4.5-0.2,6.4c-0.2,1.9-0.3,3.3-0.4,4.2c-0.1,0.7-0.7,1.3-1.4,1.3C196.5,130.5,195.4,130.6,187,131z M155.3,116.4h21.1c2.6,0,4.5,0,5.7-0.1c0.8-0.1,1.6-0.3,2.3-0.8v-1c0-1.3-0.2-2.5-0.6-3.7c-1.8-5.6-7.1-9.4-13-9.2c-5.5-0.3-10.7,2.6-13.3,7.6C156.3,111.5,155.6,114,155.3,116.4z"/>
    </g>
</svg>''',
        'alight_motion': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 172 172" xmlns="http://www.w3.org/2000/svg">
    <title>Alight Motion</title>
    <g fill="none" fill-rule="nonzero" stroke="none" stroke-width="1" stroke-linecap="butt" stroke-linejoin="miter" stroke-miterlimit="10">
        <path d="M0,172V0h172v172z" fill="none"/>
        <g fill="#1fb141">
            <path d="M21.5,21.5v129H86v-32.25v-64.5V21.5z M86,53.75C86,71.5305,100.4695,86,118.25,86C136.0305,86,150.5,71.5305,150.5,53.75C150.5,35.9695,136.0305,21.5,118.25,21.5C100.4695,21.5,86,35.9695,86,53.75z M118.25,86C100.4695,86,86,100.4695,86,118.25C86,136.0305,100.4695,150.5,118.25,150.5C136.0305,150.5,150.5,136.0305,150.5,118.25C150.5,100.4695,136.0305,86,118.25,86z"/>
        </g>
    </g>
</svg>''',
        'capcut': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 512 510" xmlns="http://www.w3.org/2000/svg">
    <title>CapCut</title>
    <path fill="#ffffff" d="M116.971 2.475h278.058c62.971 0 114.494 51.522 114.494 114.494v275.722c0 62.971-51.523 114.493-114.494 114.493H116.971c-62.972 0-114.494-51.522-114.494-114.493V116.969c0-62.972 51.522-114.494 114.494-114.494z"/>
    <path fill="#999999" fill-rule="nonzero" d="M116.97 0h278.06C459.366 0 512 52.634 512 116.969v275.722c0 64.335-52.634 116.969-116.97 116.969H116.97C52.636 509.66 0 457.026 0 392.691V116.969C0 52.633 52.636 0 116.97 0zm278.06 4.952H116.97C55.364 4.952 4.953 55.363 4.953 116.969v275.723c0 61.605 50.411 112.016 112.017 112.016h278.06c61.607 0 112.017-50.41 112.017-112.016V116.969c0-61.607-50.41-112.017-112.017-112.017z"/>
    <path fill="#000000" fill-rule="nonzero" d="M109.095 181.505c2.223-19.532 18.316-34.578 37.955-35.483l167.194-.001a40.612 40.612 0 0130.095 17.427 42.152 42.152 0 016.39 14.915l49.135-24.364a2.185 2.185 0 013.141 1.674v27.628l.001.096a4.571 4.571 0 01-2.837 4.229 177620.936 177620.936 0 00-135.63 67.336l135.324 66.948a4.695 4.695 0 013.142 4.08v27.685a2.266 2.266 0 01-3.613 1.821c-16.12-8.162-32.464-15.854-48.462-24.18a63.503 63.503 0 01-4.282 11.225 40.813 40.813 0 01-26.098 20.135 44.994 44.994 0 01-11.221.919l-155.833.003c-3.51 0-7.04 0-10.53-.266-18.089-2.705-32.049-17.363-33.869-35.565v-26.77a5.935 5.935 0 014.08-4.879c27.791-13.732 55.521-27.587 83.353-41.258a32412.61 32412.61 0 00-84.17-41.748 5.41 5.41 0 01-3.223-4.918c-.042-8.876-.185-17.792-.042-26.689zm30.975.184c-1.674 3.367-.898 7.263-1.041 10.896 30.608 15.12 60.99 30.321 91.536 45.339 30.185-14.963 60.384-29.927 90.596-44.89 0-2.714.123-5.428 0-8.162a10.203 10.203 0 00-10.096-8.734h-.106l-161.565.001a10.082 10.082 0 00-9.345 5.55h.021zm-1.041 135.406c.142 3.673-.654 7.631 1.122 11.039a10.204 10.204 0 009.284 5.405l161.667.002.081-.001c3.618 0 6.961-1.94 8.754-5.081 2.04-3.57 1.102-7.855 1.305-11.773-30.26-14.936-60.48-30.118-90.801-44.89a43915.126 43915.126 0 00-91.432 45.299h.02z"/>
</svg>''',
        'other': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <title>Other</title>
    <circle cx="12" cy="12" r="10" fill="#4B5563" opacity="0.2"/>
    <path d="M12 6a1 1 0 011 1v4h3a1 1 0 010 2h-3v4a1 1 0 01-2 0v-4H8a1 1 0 110-2h3V7a1 1 0 011-1z" fill="#4B5563"/>
</svg>'''
    }

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
    editing_tool = models.CharField(max_length=50, choices=EDITING_TOOL_CHOICES, default='other')
    
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
    rank_position_last_week = models.IntegerField(null=True, blank=True, help_text="Last week's position for trend arrows")
    rank_snapshot_at = models.DateTimeField(null=True, blank=True, help_text="When last weekly rank snapshot was taken")
    
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
        
        from django.utils import timezone
        now = timezone.now()
        for index, app in enumerate(accepted_apps, start=1):
            # Roll last week's snapshot if a week has passed or snapshot missing
            take_snapshot = False
            if app.rank_snapshot_at is None:
                take_snapshot = True
            else:
                try:
                    delta_days = (now - app.rank_snapshot_at).days
                    if delta_days >= 7:
                        take_snapshot = True
                except Exception:
                    take_snapshot = True

            if take_snapshot and app.rank_position is not None:
                app.rank_position_last_week = app.rank_position
                app.rank_snapshot_at = now

            app.rank_position = index
            app.save(update_fields=['rank_position', 'rank_position_last_week', 'rank_snapshot_at'])
    
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

    @classmethod
    def editing_tool_choices_with_svg(cls):
        return [
            {
                'value': value,
                'label': label,
                'svg': cls.EDITING_TOOL_SVG_MAP.get(value, cls.EDITING_TOOL_SVG_MAP['other'])
            }
            for value, label in cls.EDITING_TOOL_CHOICES
        ]

    def editing_tool_icon(self):
        svg = self.EDITING_TOOL_SVG_MAP.get(self.editing_tool)
        if not svg:
            svg = self.EDITING_TOOL_SVG_MAP['other']
        return mark_safe(svg)

    def rank_delta(self):
        """Positive if moved up, negative if moved down, 0 if unchanged/unknown"""
        try:
            if self.rank_position is None or self.rank_position_last_week is None:
                return 0
            return self.rank_position_last_week - self.rank_position
        except Exception:
            return 0

    def rank_trend_icon(self):
        """HTML snippet for trend arrow: up (green), down (red), dash (gray)"""
        delta = self.rank_delta()
        if delta > 0:
            # Up arrow with delta value
            return mark_safe(f'<span title="+{delta}" class="ml-2 text-green-600" aria-label="rank up">▲</span>')
        if delta < 0:
            return mark_safe(f'<span title="{delta}" class="ml-2 text-red-600" aria-label="rank down">▼</span>')
        return mark_safe('<span class="ml-2 text-gray-400" aria-label="no change">–</span>')


class EditSubmission(models.Model):
    """Model for Edit of the Week submissions"""
    
    CHANNEL_TYPE_CHOICES = [
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_submissions'
    )
    
    # Link to approved EditorApplication (channel verification)
    approved_application = models.ForeignKey(
        EditorApplication,
        on_delete=models.CASCADE,
        related_name='edit_submissions',
        help_text="The approved EditorApplication that verifies this user's channel",
        null=True,
        blank=True  # Temporarily nullable for migration, will be made required after data migration
    )
    
    # Channel info (from approved application)
    channel_link = models.URLField(max_length=500, help_text="YouTube or TikTok channel URL (from approved application)")
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    channel_name = models.CharField(max_length=200, blank=True)
    channel_thumbnail = models.URLField(max_length=500, blank=True)
    scheduled_week = models.DateField(
        null=True,
        blank=True,
        help_text="Monday (UTC) of the competition week this edit participates in"
    )
    
    # Edit information
    video_url = models.URLField(max_length=500, help_text="YouTube Shorts or TikTok video URL")
    direct_video_url = models.URLField(
        max_length=1000, 
        blank=True, 
        null=True,
        help_text="Direct video file URL (extracted via web scraping for TikTok, used for clean HTML5 video player)"
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    verified_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    upvote_count = models.IntegerField(default=0)
    report_count = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False, help_text="Featured in top 3 of the week")
    week_rank = models.IntegerField(null=True, blank=True, help_text="Rank in Edit of the Week (1-3)")
    
    # Video statistics (from platform APIs)
    views = models.BigIntegerField(default=0, help_text="Video views from platform")
    likes = models.BigIntegerField(default=0, help_text="Video likes from platform")
    comments = models.BigIntegerField(default=0, help_text="Video comments from platform")
    subscriber_count = models.BigIntegerField(default=0, help_text="Subscriber/follower count for normalization")
    
    # Points calculation
    calculated_points = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Total calculated points for ranking"
    )
    last_points_calculation = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last time points were calculated"
    )
    weeks_participated = models.IntegerField(
        default=1,
        help_text="Number of consecutive weeks user has submitted edits"
    )
    
    class Meta:
        ordering = ['-calculated_points', '-submitted_date']
        
    def __str__(self):
        return f"{self.user.username} - {self.title or self.video_url} ({self.get_status_display()})"
    
    def update_upvote_count(self):
        """Update upvote count from related upvotes and recalculate points"""
        self.upvote_count = self.upvotes.filter(is_active=True).count()
        # Recalculate points when upvotes change (upvotes contribute to points)
        self.calculated_points = self.calculate_points()
        self.save(update_fields=['upvote_count', 'calculated_points'])
    
    def update_report_count(self):
        """Update report count from related reports"""
        self.report_count = self.reports.filter(is_active=True).count()
        self.save(update_fields=['report_count'])
    
    def calculate_points(self):
        """
        Calculate total points based on platform performance and community feedback.
        Returns the calculated points value.
        """
        from .utils import calculate_youtube_points, calculate_tiktok_points
        
        # Base platform points
        if self.channel_type == 'youtube':
            platform_points = calculate_youtube_points(
                self.views, self.likes, self.comments, self.subscriber_count
            )
        elif self.channel_type == 'tiktok':
            platform_points = calculate_tiktok_points(
                self.views, self.likes, self.comments, self.subscriber_count
            )
        else:
            platform_points = 0.0
        
        # Upvote points (max 50)
        upvote_points = min(self.upvote_count * 2, 50)
        
        # Continuous participation bonus (15 pts per week)
        participation_points = (self.weeks_participated - 1) * 15
        
        # Total points
        total_points = platform_points + upvote_points + participation_points
        
        return float(total_points)


class EditUpvote(models.Model):
    """Model for tracking user upvotes on edits (max 3 per user)"""
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_upvotes'
    )
    
    edit_submission = models.ForeignKey(
        EditSubmission,
        on_delete=models.CASCADE,
        related_name='upvotes'
    )
    
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'edit_submission')
        ordering = ['-created_date']
    
    def __str__(self):
        return f"{self.user.username} upvoted {self.edit_submission}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.edit_submission.update_upvote_count()
    
    def delete(self, *args, **kwargs):
        edit_submission = self.edit_submission
        super().delete(*args, **kwargs)
        edit_submission.update_upvote_count()


class EditReport(models.Model):
    """Model for reporting explicit or inappropriate edits"""
    
    REPORT_REASON_CHOICES = [
        ('explicit', 'Explicit Content'),
        ('spam', 'Spam'),
        ('copyright', 'Copyright Violation'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_reports'
    )
    
    edit_submission = models.ForeignKey(
        EditSubmission,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    
    reason = models.CharField(max_length=50, choices=REPORT_REASON_CHOICES)
    description = models.TextField(blank=True, help_text="Additional details")
    is_active = models.BooleanField(default=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_reports',
        limit_choices_to={'role': 'admin'}
    )
    resolved_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'edit_submission')
        ordering = ['-created_date']
    
    def __str__(self):
        return f"Report on {self.edit_submission} by {self.user.username} - {self.get_reason_display()}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.edit_submission.update_report_count()
    
    def delete(self, *args, **kwargs):
        edit_submission = self.edit_submission
        super().delete(*args, **kwargs)
        edit_submission.update_report_count()


# Signal to keep EditSubmission thumbnails in sync with EditorApplication
# This will be connected at the end of the file after EditSubmission is defined
def update_edit_submission_thumbnails_signal(sender, instance, **kwargs):
    """
    When EditorApplication thumbnail or channel_name is updated,
    automatically update all related EditSubmissions to keep them in sync.
    This ensures banner images always show the latest profile pictures.
    """
    # Only update if this is an accepted application
    if instance.status == 'accepted' and not instance.removal_requested:
        # Update all EditSubmissions that reference this EditorApplication
        EditSubmission.objects.filter(
            approved_application=instance,
            status='verified'
        ).update(
            channel_thumbnail=instance.channel_thumbnail or '',
            channel_name=instance.channel_name or ''
        )
        
        # Also update EditSubmissions that don't have approved_application but match user/channel
        EditSubmission.objects.filter(
            user=instance.user,
            channel_type=instance.channel_type,
            status='verified',
            approved_application__isnull=True
        ).update(
            channel_thumbnail=instance.channel_thumbnail or '',
            channel_name=instance.channel_name or ''
        )

# Connect the signal after EditSubmission is defined
post_save.connect(update_edit_submission_thumbnails_signal, sender=EditorApplication)


class Tournament(models.Model):
    """Model for Tournament of Editors - Semi-Finals"""
    
    name = models.CharField(max_length=200, default="Tournament of Editors", help_text="Tournament name")
    is_active = models.BooleanField(default=True, help_text="Only one active tournament should exist")
    
    # Semi-Final 1 participants
    participant_1 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_1',
        help_text="Semi-Final 1 - First participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_2 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_2',
        help_text="Semi-Final 1 - Second participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    
    # Semi-Final 2 participants
    participant_3 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_3',
        help_text="Semi-Final 2 - First participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_4 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_4',
        help_text="Semi-Final 2 - Second participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_active', '-created_date']
        verbose_name = "Tournament"
        verbose_name_plural = "Tournaments"
    
    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"
    
    def get_participants(self):
        """Return list of participants in order"""
        return [
            self.participant_1,
            self.participant_2,
            self.participant_3,
            self.participant_4,
        ]
    
    def save(self, *args, **kwargs):
        # If this tournament is being set as active, deactivate all others
        if self.is_active:
            Tournament.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_tournament(cls):
        """Get the currently active tournament"""
        return cls.objects.filter(is_active=True).first()