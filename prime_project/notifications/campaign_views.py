from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from .campaigns import token_user, unsubscribe


def private_response(response):
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def unsubscribe_confirmation(request, token):
    user = token_user(token)
    if not user:
        return private_response(render(request, 'notifications/member_unsubscribe.html', {'invalid': True}, status=400))
    done = request.method == 'POST'
    if done:
        unsubscribe(user)
    return private_response(render(request, 'notifications/member_unsubscribe.html', {'done': done}))


@csrf_exempt
@never_cache
@require_POST
def one_click(request, token):
    # The signed bearer URL authenticates this RFC 8058 POST; no login/cookie needed.
    user = token_user(token)
    if not user or request.POST.get('List-Unsubscribe') != 'One-Click':
        return private_response(HttpResponse('Invalid unsubscribe request.', status=400))
    unsubscribe(user)
    return private_response(HttpResponse('Member email campaigns unsubscribed.'))
