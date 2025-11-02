from django import template
from django.utils.safestring import mark_safe

register = template.Library()

try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


@register.filter
def markdown_to_html(text):
    """Convert markdown text to HTML."""
    if not text:
        return ""
    
    if not MARKDOWN_AVAILABLE:
        # Fallback to plain text with line breaks if markdown is not available
        return mark_safe(text.replace('\n', '<br>'))
    
    try:
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        return mark_safe(md.convert(text))
    except Exception:
        # Fallback to plain text if markdown conversion fails
        return mark_safe(text.replace('\n', '<br>'))

