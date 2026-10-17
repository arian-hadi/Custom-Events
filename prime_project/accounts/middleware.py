from ipaddress import ip_address
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from django.conf import settings
from django.http import HttpResponseRedirect


def v2_editor_destination(path, query):
    normalized = path.rstrip('/')
    member_pages = {
        '/accounts/profile': '/account/profile', '/editinghub/customize-profile': '/account/profile',
        '/dashboard': '/account', '/dashboard/user': '/account',
        '/dashboard/user/applications': '/applications', '/editinghub/edits': '/account/edits',
        '/editinghub/submit-edit': '/editing-hub#league-rounds', '/editinghub/confirm-edit': '/account/edits',
        '/editinghub': '/editing-hub', '/events/events': '/events',
        '/accounts/signup': '/register', '/accounts/password-reset': '/forgot-password',
        '/accounts/password-reset/done': '/forgot-password', '/accounts/password-reset-complete': '/login',
    }
    if normalized in member_pages:
        return member_pages[normalized]
    if normalized == '/accounts/verify-email':
        return '/verify-email?' + urlencode({'email': query.get('email', [''])[0]})
    match = re.fullmatch(r'/accounts/password-reset-confirm/([^/]+)/([^/]+)/?', path)
    if match:
        return '/reset-password?' + urlencode({'uid': match.group(1), 'token': match.group(2)})
    match = re.fullmatch(r'/dashboard/application/(\d+)(?:/edit)?/?', path)
    if match:
        return f'/applications/events/{match.group(1)}'
    match = re.fullmatch(r'/editinghub/edit-submission/(\d+)/(?:edit|preview|success)/?', path)
    if match:
        return f'/account/edits/{match.group(1)}'
    match = re.fullmatch(r'/events/events/(\d+)(?:/apply)?/?', path)
    if match:
        return f'/events/{match.group(1)}'
    if path.rstrip('/') == '/editinghub/apply':
        platform = query.get('platform', query.get('edit_platform', ['youtube']))[0]
        return '/editing-hub/apply?' + urlencode({'platform': 'tiktok' if platform == 'tiktok' else 'youtube'})
    if path.rstrip('/') == '/editinghub/confirm':
        return '/applications'
    match = re.fullmatch(r'/editinghub/application/(\d+)(?:/remove)?/?', path)
    if match:
        return f'/applications/editors/{match.group(1)}'
    return None


class V2EditorApplicationRedirectMiddleware:
    """Route bookmarked editor pages to V2 only on V2 deployments; keep old POSTs intact."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in {'GET', 'HEAD'} and (
            getattr(settings, 'V2_TRUST_GATEWAY_ADDRESS', False) or getattr(settings, 'V2_LOCAL_PREVIEW', False)
        ):
            destination = v2_editor_destination(request.path, dict(request.GET.lists()))
            if request.path.rstrip('/') == '/accounts/login':
                try:
                    target = urlsplit(request.GET.get('next', ''))
                except ValueError:
                    return self.get_response(request)
                if not target.scheme and not target.netloc:
                    next_page = v2_editor_destination(target.path, parse_qs(target.query))
                    if not next_page and target.path.startswith('/') and not target.path.startswith('//') and '\\' not in target.path:
                        next_page = target.path + ('?' + target.query if target.query else '')
                    # Django admin keeps its own login workflow.
                    if not target.path.startswith('/admin'):
                        destination = '/login?' + urlencode({'next': next_page or '/account'})
            if destination:
                return HttpResponseRedirect(settings.V2_FRONTEND_URL.rstrip('/') + destination)
        return self.get_response(request)


class TrustedGatewayAddressMiddleware:
    """Opt-in for a private backend reached only through our gateway.

    The V2 gateway replaces X-Real-IP with its own peer address. Never enable
    this setting when clients can reach Django directly or a proxy forwards
    the incoming header unchanged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'V2_TRUST_GATEWAY_ADDRESS', False):
            try:
                request.META['REMOTE_ADDR'] = str(ip_address(request.META.get('HTTP_X_REAL_IP', '')))
            except ValueError:
                pass
        return self.get_response(request)
