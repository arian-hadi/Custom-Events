"""Private editorial workspace. Discovery never publishes a blog post."""
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class YouTubeBlogChannel(models.Model):
    name = models.CharField(max_length=150, help_text="A name for this channel in your admin panel.")
    channel_url = models.URLField(help_text="Your YouTube /@handle or /channel/UC… URL.")
    automatic_checks = models.BooleanField(default=False, help_text="Check for videos on the background worker. Manual checks are always available.")
    fetch_captions = models.BooleanField(default=False, help_text="Requires owner OAuth credentials. You can also paste/upload your script on each video.")
    notify_admins = models.BooleanField(default=True, help_text="Email the recipients in Admin email settings once per newly discovered video.")
    check_interval_minutes = models.PositiveIntegerField(default=60, validators=[MinValueValidator(15), MaxValueValidator(10080)])
    language = models.CharField(max_length=20, default="en")
    writing_instructions = models.TextField(blank=True, help_text="Audience, tone and other instructions included in the downloadable AI brief.")
    channel_id = models.CharField(max_length=100, blank=True, editable=False)
    uploads_playlist_id = models.CharField(max_length=100, blank=True, editable=False)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    next_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.CharField(max_length=500, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "YouTube channel"
        verbose_name_plural = "YouTube channels"

    def __str__(self):
        return self.name


class YouTubeBlogVideo(models.Model):
    channel = models.ForeignKey(YouTubeBlogChannel, on_delete=models.PROTECT, related_name="videos")
    video_id = models.CharField(max_length=11, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    thumbnail_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True, help_text="Your complete script or downloaded captions. This is source material, not the published article.")
    transcript_source = models.CharField(max_length=30, blank=True, editable=False)
    transcript_error = models.CharField(max_length=500, blank=True, editable=False)
    caption_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    instructions = models.TextField(blank=True, help_text="Extra instructions for this particular article.")
    blog_post = models.OneToOneField("platform_api.BlogPost", null=True, blank=True, on_delete=models.SET_NULL, related_name="youtube_source", editable=False)
    discovered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def video_url(self):
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def preparation_status(self):
        if self.blog_post_id:
            return "Published" if self.blog_post.status == "published" else "Blog draft ready"
        return "Ready for AI brief" if self.transcript.strip() else "Needs script"

    class Meta:
        ordering = ["-published_at", "-pk"]
        verbose_name = "YouTube → Blog video"
        verbose_name_plural = "YouTube → Blog workspace"

    def __str__(self):
        return self.title


class YouTubeBlogSuppression(models.Model):
    """Remember explicitly deleted source items so scheduled checks stay quiet."""
    channel = models.ForeignKey(YouTubeBlogChannel, on_delete=models.CASCADE)
    video_id = models.CharField(max_length=11, unique=True)
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)


class BlogMarkdownImport(models.Model):
    video = models.ForeignKey(YouTubeBlogVideo, on_delete=models.SET_NULL, null=True, blank=True, related_name="imports")
    post = models.ForeignKey("platform_api.BlogPost", on_delete=models.SET_NULL, null=True, blank=True)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    original_markdown = models.TextField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Blog Markdown import"
        verbose_name_plural = "Blog Markdown import history"

    def __str__(self):
        return f"{self.video.title if self.video_id else 'Deleted source video'} · {self.created_at}"
