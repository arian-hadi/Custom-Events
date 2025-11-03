from django import template
import re

register = template.Library()


@register.filter(name="youtube_embed")
def youtube_embed(url: str) -> str:
    """Convert a YouTube/Shorts URL to an embeddable URL.
    Handles various YouTube URL formats and extracts video ID.
    """
    if not url:
        return ""

    video_id = None
    
    try:
        # Shorts: https://www.youtube.com/shorts/<id>
        m = re.search(r"youtube\.com/shorts/([\w-]{11})", url)
        if m:
            video_id = m.group(1)
        else:
            # Watch: https://www.youtube.com/watch?v=<id> or https://youtube.com/watch?v=<id>
            m = re.search(r"[?&]v=([\w-]{11})", url)
            if m:
                video_id = m.group(1)
            else:
                # youtu.be/<id>
                m = re.search(r"youtu\.be/([\w-]{11})", url)
                if m:
                    video_id = m.group(1)
                else:
                    # Embed URL: already an embed URL
                    m = re.search(r"youtube\.com/embed/([\w-]{11})", url)
                    if m:
                        video_id = m.group(1)
        
        if video_id:
            # Use privacy-enhanced domain; avoid autoplay/jsapi to reduce embed errors
            return f"https://www.youtube-nocookie.com/embed/{video_id}?modestbranding=1&rel=0&playsinline=1"
    except Exception:
        pass

    # If we can't parse it, return original (user can check the link)
    return url


@register.filter(name="youtube_thumbnail")
def youtube_thumbnail(url: str) -> str:
    """Extract YouTube video ID and return thumbnail URL."""
    if not url:
        return ""
    
    video_id = None
    try:
        # Try to extract video ID using same logic as youtube_embed
        m = re.search(r"youtube\.com/shorts/([\w-]{11})", url)
        if m:
            video_id = m.group(1)
        else:
            m = re.search(r"[?&]v=([\w-]{11})", url)
            if m:
                video_id = m.group(1)
            else:
                m = re.search(r"youtu\.be/([\w-]{11})", url)
                if m:
                    video_id = m.group(1)
                else:
                    m = re.search(r"youtube\.com/embed/([\w-]{11})", url)
                    if m:
                        video_id = m.group(1)
        
        if video_id:
            return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    except Exception:
        pass
    
    return ""


@register.filter(name="youtube_watch")
def youtube_watch(url: str) -> str:
    """Normalize to a standard YouTube watch URL from various formats."""
    if not url:
        return ""
    vid = None
    for pattern in [
        r"youtube\.com/shorts/([\w-]{11})",
        r"[?&]v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"youtube\.com/embed/([\w-]{11})",
    ]:
        m = re.search(pattern, url)
        if m:
            vid = m.group(1)
            break
    return f"https://www.youtube.com/watch?v={vid}" if vid else url


