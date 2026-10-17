"""Shared, escaped HTML presentation. Delivery and consent stay with each caller."""
import re

from django.template.loader import render_to_string
from django.utils.html import format_html


def email_html(title, content, *, action_url='', action_label='View details', code=''):
    from platform_api.models import SiteSettings

    site = SiteSettings.objects.first()
    accent = getattr(site, 'accent_color', '#ef233c')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent or ''):
        accent = '#ef233c'
    return render_to_string('notifications/email_branded.html', {
        'brand': getattr(site, 'name', '') or '2.0Transformers',
        'accent': accent, 'title': title, 'content': content,
        'action_url': action_url, 'action_label': action_label, 'code': code,
    })


def text_content(body):
    return format_html('<div style="white-space:pre-line;overflow-wrap:anywhere">{}</div>', body)
