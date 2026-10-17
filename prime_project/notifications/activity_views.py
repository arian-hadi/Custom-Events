"""Signed opt-out endpoints; GET previews and never changes preferences."""
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from .activity_email import token_user, unsubscribe
from .campaign_views import private_response


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def unsubscribe_confirmation(request, token):
    user = token_user(token)
    context = {'activity': True, 'invalid': not user, 'done': bool(user and request.method == 'POST')}
    if context['done']:
        unsubscribe(user)
    return private_response(render(request, 'notifications/member_unsubscribe.html', context, status=200 if user else 400))


@csrf_exempt
@never_cache
@require_POST
def one_click(request, token):
    user = token_user(token)
    if not user or request.POST.get('List-Unsubscribe') != 'One-Click':
        return private_response(HttpResponse('Invalid unsubscribe request.', status=400))
    unsubscribe(user)
    return private_response(HttpResponse('Optional member emails unsubscribed.'))
