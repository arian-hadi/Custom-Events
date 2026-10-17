from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from edithub.league.preview import STATES, preview_enabled, sample_league, valid_token


@never_cache
@require_GET
def preview(request):
    if not preview_enabled():
        return JsonResponse({'error': 'Local preview is unavailable.'}, status=404)
    if not valid_token(request.GET.get('token', '')):
        return JsonResponse({'error': 'This preview link is missing, invalid or expired. Run league_preview again for a new link.'}, status=403)
    state = request.GET.get('state', 'live')
    if state not in STATES:
        return JsonResponse({'error': 'Choose live, frozen, or pending.'}, status=400)
    return JsonResponse(sample_league(state))
