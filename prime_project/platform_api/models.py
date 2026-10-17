import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.validators import validate_image_file_size


def default_navigation():
    return [
        {"label": "Home", "url": "/"},
        {"label": "Shop", "url": "/store"},
        {"label": "Blog", "url": "/news"},
        {"label": "Editing Hub", "url": "/editing-hub"},
        {"label": "Events", "url": "/events"},
        {"label": "Contact", "url": "/contact"},
    ]


def default_home_sections():
    return [
        {"key": "access", "title": "Explore the collection", "body": "Discover products selected for our community.", "button_text": "Visit the shop", "button_url": "/store"},
        {"key": "community", "title": "Find your community", "body": "Catch up on the latest stories, announcements, and events.", "button_text": "Read the blog", "button_url": "/news"},
        {"key": "features", "title": "A space for editors", "body": "The next chapter of the Editing Hub is taking shape.", "button_text": "Editing Hub", "button_url": "/editing-hub"},
    ]


def validate_home_sections(value):
    if not isinstance(value, list) or len(value) > 10:
        raise ValidationError("Enter a list of at most 10 homepage sections.")
    keys = set()
    for section in value:
        if not isinstance(section, dict) or set(section) != {"key", "title", "body", "button_text", "button_url"}:
            raise ValidationError("Each section needs key, title, body, button_text, and button_url.")
        if not all(isinstance(item, str) for item in section.values()):
            raise ValidationError("Section values must be text.")
        if section["key"] in keys or not section["key"] or len(section["key"]) > 80:
            raise ValidationError("Section keys must be unique and contain 1 to 80 characters.")
        keys.add(section["key"])
        if len(section["title"]) > 200 or len(section["body"]) > 5000 or len(section["button_text"]) > 80:
            raise ValidationError("Section text is too long.")
        validate_link(section["button_url"])


def validate_link(value):
    if not isinstance(value, str) or not value or "\\" in value or any(c.isspace() for c in value):
        raise ValidationError("Use a relative path or an HTTP(S) URL.")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValidationError("Use a valid relative path or HTTP(S) URL.") from exc
    if value.startswith("/") and not value.startswith("//"):
        return
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("Use a relative path or an HTTP(S) URL.")


def validate_links(value):
    if not isinstance(value, list) or len(value) > 20:
        raise ValidationError("Enter a list of at most 20 links.")
    for link in value:
        if not isinstance(link, dict) or set(link) != {"label", "url"}:
            raise ValidationError('Each link needs exactly "label" and "url".')
        if not isinstance(link["label"], str) or not link["label"].strip() or len(link["label"]) > 80:
            raise ValidationError("Link labels must contain 1 to 80 characters.")
        validate_link(link["url"])


def validate_buy_me_a_coffee_url(value):
    """Keep the branded support button pointed at an actual profile URL."""
    message = "Use your HTTPS Buy Me a Coffee profile link, such as https://buymeacoffee.com/yourname."
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in {"buymeacoffee.com", "www.buymeacoffee.com"}
            and not parsed.username
            and not parsed.password
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_.-]+/?", parsed.path)
            and "\\" not in value
            and not any(character.isspace() for character in value)
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValidationError(message)


class SiteSettings(models.Model):
    """One admin-managed configuration; public GETs never create records."""

    name = models.CharField(max_length=120, default="2.0 Transformers")
    accent_color = models.CharField(
        max_length=7, default="#ef233c",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a six-digit hex color, such as #ef233c.")],
        help_text="Main accent for links, highlights, buttons and competition details.",
    )
    secondary_accent_color = models.CharField(
        max_length=7, default="#ffb800",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a six-digit hex color, such as #ffb800.")],
        help_text="Secondary accent blended with the main color for button gradients and background glows.",
    )
    hero_title = models.CharField(max_length=200, default="Create. Connect. Transform.")
    hero_subtitle = models.TextField(default="Discover edits, explore the shop, and join the community.")
    hero_image = models.ImageField(upload_to="site/hero/", blank=True, validators=[validate_image_file_size])
    hero_button_text = models.CharField(max_length=80, default="Explore the shop")
    hero_button_url = models.CharField(max_length=500, default="/store", validators=[validate_link])
    footer_text = models.CharField(max_length=300, default="A community for creators and Transformers fans.")
    buy_me_a_coffee_url = models.URLField(
        "Buy Me a Coffee profile link", max_length=500, blank=True, default="",
        validators=[validate_buy_me_a_coffee_url],
        help_text="Optional. Set your profile link to show the footer support button; leave blank to hide it.",
    )
    navigation = models.JSONField(default=default_navigation, validators=[validate_links])
    social_links = models.JSONField(default=list, blank=True, validators=[validate_links])
    home_sections = models.JSONField(default=default_home_sections, blank=True, validators=[validate_home_sections])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Website settings"
        verbose_name_plural = "Website settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Website appearance and content"


class BlogPost(models.Model):
    STATUS_CHOICES = [("draft", "Draft"), ("published", "Published")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField(help_text="Article content. Basic rich text is supported.")
    category = models.CharField(max_length=80, blank=True)
    cover_image = models.ImageField(upload_to="blog/covers/", blank=True, validators=[validate_image_file_size])
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="draft")
    published_at = models.DateTimeField(default=timezone.now, help_text="Published posts appear after this time.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-pk"]
        indexes = [models.Index(fields=["status", "published_at"], name="blog_publication_idx")]

    def __str__(self):
        return self.title


from .youtube_models import YouTubeBlogChannel, YouTubeBlogVideo, YouTubeBlogSuppression, BlogMarkdownImport  # noqa: E402,F401
