from django import template
import re

register = template.Library()


@register.filter(name="tiktok_embed_url")
def tiktok_embed_url(url: str) -> str:
    """
    Convert a TikTok video URL to an embeddable URL.
    Expected input formats include:
      - https://www.tiktok.com/@username/video/1234567890123456789
      - https://m.tiktok.com/v/1234567890123456789.html (best-effort)
    Returns:
      - https://www.tiktok.com/embed/v2/video/<video_id>
      - or original URL if parsing fails
    """
    if not url:
        return ""

    # Standard TikTok pattern
    m = re.search(r"tiktok\.com/@[^/]+/video/(\d+)", url)
    if m:
        return f"https://www.tiktok.com/embed/v2/video/{m.group(1)}"

    # Legacy/m-dot patterns (best-effort)
    m = re.search(r"tiktok\.com/(?:v|embed)/?(\d+)", url)
    if m:
        return f"https://www.tiktok.com/embed/v2/video/{m.group(1)}"

    return url


