from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from datetime import timedelta
from .manager import UserManager

# Custom User Model
class CustomUser(AbstractUser):
    # Remove first_name and last_name by overriding them
    first_name = None
    last_name = None

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('user', 'User'),
    )

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)  
    role = models.CharField(choices=ROLE_CHOICES, default='user', max_length=10)
    is_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # Profile display preferences
    PROFILE_DISPLAY_CHOICES = [
        ('account', 'Account Profile'),
        ('channel', 'Channel Profile'),
    ]
    
    profile_display_mode = models.CharField(
        max_length=20,
        choices=PROFILE_DISPLAY_CHOICES,
        default='account',
        help_text="Display account profile or channel profile"
    )
    
    profile_channel_source = models.CharField(
        max_length=20,
        choices=[('youtube', 'YouTube'), ('tiktok', 'TikTok')],
        blank=True,
        null=True,
        help_text="Which channel to use for profile display (if user has both YouTube and TikTok)"
    )
    
    # Unified editor title (applies to all platforms)
    selected_title = models.ForeignKey(
        'edithub.EditorTitle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="Selected editor title that applies to all platforms (YouTube and TikTok)"
    )
    
    # Mix ranking fields (for combined YouTube + TikTok ranking)
    mix_rank_position = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="Position in mix ranking table (combines YouTube + TikTok followers)"
    )
    mix_rank_position_last_week = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="Last week's mix rank position for trend arrows"
    )
    mix_rank_snapshot_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="When last weekly mix rank snapshot was taken"
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Only 'username' will be required

    objects = UserManager()

    def __str__(self):
        return self.email
    
    def is_member(self):
        return self.role == 'member'
    
    def is_admin(self):
        return self.role == 'admin'
    
    def get_display_name(self):
        """
        Get the display name based on profile_display_mode.
        Returns account username or channel name.
        """
        if self.profile_display_mode == 'channel':
            from edithub.models import EditorApplication
            # Get primary application (highest follower count)
            app = EditorApplication.objects.filter(
                user=self,
                status='accepted',
                removal_requested=False
            ).order_by('-follower_count').first()
            
            if app and app.channel_name:
                return app.channel_name
        
        # Default to account username
        return self.username
    
    def get_display_picture(self):
        """
        Get the display picture URL based on profile_display_mode.
        Returns account profile picture or channel thumbnail.
        """
        if self.profile_display_mode == 'channel':
            from edithub.models import EditorApplication
            # Get primary application (highest follower count)
            app = EditorApplication.objects.filter(
                user=self,
                status='accepted',
                removal_requested=False
            ).order_by('-follower_count').first()
            
            if app and app.channel_thumbnail:
                return app.channel_thumbnail
        
        # Default to account profile picture
        if self.profile_picture:
            return self.profile_picture.url
        return None
    
    def get_available_channels(self):
        """
        Get list of available channel applications for profile switching.
        Returns list of dicts with channel info.
        """
        from edithub.models import EditorApplication
        apps = EditorApplication.objects.filter(
            user=self,
            status='accepted',
            removal_requested=False
        ).order_by('-follower_count')
        
        channels = []
        for app in apps:
            channels.append({
                'type': app.channel_type,
                'name': app.channel_name,
                'thumbnail': app.channel_thumbnail,
                'follower_count': app.follower_count,
            })
        
        return channels
    
    def mix_rank_delta(self):
        """Positive if moved up, negative if moved down, 0 if unchanged/unknown"""
        try:
            if self.mix_rank_position is None or self.mix_rank_position_last_week is None:
                return 0
            return self.mix_rank_position_last_week - self.mix_rank_position
        except Exception:
            return 0
    
    def mix_rank_trend_icon(self):
        """HTML snippet for mix rank trend arrow: up (green), down (red), dash (gray)"""
        from django.utils.safestring import mark_safe
        delta = self.mix_rank_delta()
        if delta > 0:
            # Up arrow with delta value - using darker green for better visibility
            return mark_safe(f'<span title="+{delta}" class="ml-2 text-green-700 font-semibold" aria-label="mix rank up">▲</span>')
        if delta < 0:
            return mark_safe(f'<span title="{delta}" class="ml-2 text-red-600 font-semibold" aria-label="mix rank down">▼</span>')
        return mark_safe('<span class="ml-2 text-gray-400" aria-label="no change">–</span>')

# One-Time Password Model
class OneTimePassword(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=now)

    class Meta:
        # At most one active code per user; allow different users to share the same 6-digit code.
        unique_together = ('user', 'code')
        indexes = [
            models.Index(fields=['user', 'code']),
            models.Index(fields=['created_at']),
    ]

    def is_expired(self):
        return self.created_at < now() - timedelta(minutes=10)

    def __str__(self):
        return f"{self.user.username} passcode"


        


