"""Read-only league presentation and authenticated, deadline-locked intake."""
import logging
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.api_views import limited
from edithub.models import EditorApplication
from edithub.league_models import (
    CompetitionEntry, CompetitionWeek, LeagueSeason, MetricSnapshot,
    MonthlyAward, WeeklyResult,
)
from edithub.league.calendar import monday_for, next_week_start
from edithub.league.integration import ProviderSetupRequired, fetch_verified_video
from edithub.league.scoring import age_band, is_cohort, validate_config, version_ready
from edithub.league.automation import league_enabled
from edithub.league.providers import ProviderError
from edithub.league import services
from .views import endpoint, payload
from .member_titles import title_data

logger = logging.getLogger(__name__)


def ready(week):
    return bool(week and version_ready(week.scoring_version))


def week_data(week):
    if week is None:
        return None
    state = week.state
    if state not in services.FINAL_STATES and timezone.now() >= week.cutoff_at:
        state = 'finalizing'
    last = week.last_observed_at if hasattr(week, 'last_observed_at') else MetricSnapshot.objects.filter(entry__week=week).aggregate(value=Max('completed_at'))['value']
    return {
        'id': week.pk, 'label': f'{week.start_at:%d %b} – {week.cutoff_at - timedelta(days=1):%d %b %Y}',
        'starts_at': week.start_at, 'cutoff_at': week.cutoff_at,
        'competition_month': week.scoring_date.strftime('%Y-%m'),
        'ends_at': week.start_at + timedelta(days=7), 'state': state,
        'last_refresh': last, 'result_revision': week.current_revision,
        'scoring_method': week.scoring_version.config.get('mapping_policy'),
        'debut_improvement_score': week.scoring_version.config.get('debut_improvement_score'),
    }


def selected_weeks(now):
    current, upcoming = monday_for(now), next_week_start(now)
    weeks = {week.start_at: week for week in CompetitionWeek.objects.select_related('scoring_version', 'season')
             .filter(start_at__in=[current, upcoming])}
    return weeks.get(current), weeks.get(upcoming)


@endpoint()
def rounds(request):
    """Public calendar metadata without exposing queued submissions or audit data."""
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    if not 2000 <= year <= 2200:
        return JsonResponse({'error': 'Invalid calendar year.'}, status=400)
    official = WeeklyResult.objects.filter(week_id=OuterRef('pk'), revision=OuterRef('current_revision'), placement__isnull=False)
    weeks = CompetitionWeek.objects.filter(scoring_date__year=year).select_related('season', 'scoring_version').annotate(
        public_entry_count=Count('entries', filter=Q(entries__state__in=['active', 'data_pending']), distinct=True),
        last_observed_at=Max('entries__snapshots__completed_at'),
        has_results=Exists(official),
    ).order_by('-start_at', '-pk')
    data = [{**week_data(week), 'calendar_year': week.scoring_date.year, 'entry_count': week.public_entry_count,
             'official_results': bool(week.state == 'finalized' and ready(week) and week.has_results)} for week in weeks]
    current, upcoming = selected_weeks(now)
    months = {int(row['competition_month'][5:7]) for row in data
              if row['competition_month'] <= now.strftime('%Y-%m')}
    months.update(MonthlyAward.objects.filter(year=year, effective=True).values_list('month', flat=True))
    if year == now.year:
        months.add(now.month)
    return JsonResponse({
        'years': [{'id': season.pk, 'year': season.year, 'name': str(season.year)} for season in LeagueSeason.objects.order_by('-year')],
        'selected_year': year, 'rounds': data,
        'months': [{'month': month, 'label': date(year, month, 1).strftime('%B %Y')}
                   for month in sorted(months, reverse=True)],
        'current_week_id': current.pk if current else None, 'next_week_id': upcoming.pk if upcoming else None,
    })


@endpoint()
def status(request):
    now = timezone.now()
    current, upcoming = selected_weeks(now)
    enabled = league_enabled()
    configured = ready(upcoming or current)
    can_submit = bool(enabled and ready(upcoming) and upcoming.state == 'scheduled' and now < upcoming.start_at)
    reason = '' if can_submit else (
        'The league is being prepared. Entries will open when the rules and scoring setup are ready.'
        if not enabled or not configured else 'Entry registration for the next round is not open yet.'
    )
    current_data = week_data(current)
    return JsonResponse({
        'enabled': enabled, 'configuration_ready': configured, 'can_submit': can_submit, 'reason': reason,
        'repeat_policy': 'one_per_month',
        'current_week': current_data, 'next_week': week_data(upcoming),
        'month': {'year': now.year, 'month': now.month, 'name': now.strftime('%B %Y')},
        'last_refresh': current_data['last_refresh'] if current_data else None,
        'scoring_method': (current or upcoming).scoring_version.config.get('mapping_policy') if current or upcoming else None,
        'scoring_validated': bool((current or upcoming).scoring_version.calibrated) if current or upcoming else False,
        'debut_improvement_score': (current or upcoming).scoring_version.config.get('debut_improvement_score') if current or upcoming else None,
        'placement_points': (current or upcoming).scoring_version.config['placement_points'] if current or upcoming else [],
        'finisher_points': (current or upcoming).scoring_version.config['finisher_points'] if current or upcoming else None,
        'minimum_entries': (current or upcoming).scoring_version.config['minimum_entries'] if current or upcoming else None,
        'weights': ((current or upcoming).scoring_version.config.get('weights', {}) if current or upcoming else
                    {'response': '0.50', 'improvement': '0.30', 'popularity': '0.20'}),
    })


def entry_identity(entry):
    application = entry.approved_application
    verified = bool(application and application.status == 'accepted' and application.channel_verified and not application.removal_requested)
    return {'platform': entry.platform, 'channel_name': application.channel_name if verified else None,
            **title_data(entry.editor, application),
            'channel_verified': verified, 'profile_picture': entry.editor.profile_picture.url if entry.editor.profile_picture else None,
            'rank_change': None}


def score_metadata(config, values, baseline=None):
    """Labels follow the recorded version, including old likes-based results."""
    debut = bool(values.get('debut_bonus'))
    return {
        'scoring_method': config.get('mapping_policy'),
        'popularity_metric': 'views' if config.get('mapping_policy') == 'round_cohort_v2' else 'likes',
        'baseline_policy': config.get('baseline_policy', 'channel_age_matched'),
        'baseline_sample_count': baseline.sample_count if baseline else values.get('baseline_sample_count'),
        'baseline_median_likes': baseline.median_likes if baseline else values.get('baseline_median_likes'),
        'neutral_baseline': bool(values.get('neutral_improvement', baseline is not None and baseline.median_likes is None)) and not debut,
        'debut_bonus': debut, 'improvement_weight': config['weights']['improvement'],
        **{key: values.get(key) for key in ('likes', 'views', 'relative_performance')},
    }


def result_row(result):
    entry = result.entry
    return {
        'editor_id': entry.editor_id, 'username': entry.editor.username, 'entry_id': entry.pk,
        'rank': result.placement, 'points': result.league_points, 'weekly_score': result.weekly_score,
        'response_score': result.response_score, 'improvement_score': result.improvement_score,
        'popularity_score': result.popularity_score, 'video_url': entry.canonical_url,
        **score_metadata(result.week.scoring_version.config, result.details, result.baseline),
        'last_refresh': result.snapshot.completed_at if result.snapshot else None,
        'data_pending': False, **entry_identity(entry),
    }


@endpoint()
def standings(request):
    period = request.GET.get('period', 'week')
    if period not in {'week', 'month', 'all_time'}:
        return JsonResponse({'error': 'Choose week, month or all_time. Annual competition is retired.'}, status=400)
    now = timezone.now()
    current, _ = selected_weeks(now)
    if period == 'week':
        week = current
        if request.GET.get('week'):
            week = get_object_or_404(CompetitionWeek.objects.select_related('scoring_version'), pk=request.GET['week'])
        if week is None:
            return JsonResponse({'period': period, 'period_label': 'Upcoming league', 'state': 'scheduled', 'provisional': True, 'rows': [], 'last_refresh': None})
        frozen = week.state in {'finalized', 'exhibition', 'canceled'}
        rows = []
        if week.state == 'finalized' and ready(week):
            results = WeeklyResult.objects.filter(week=week, revision=week.current_revision, placement__isnull=False).select_related('entry__editor__selected_title', 'entry__approved_application__selected_title', 'baseline', 'snapshot', 'week__scoring_version').order_by('placement')
            rows = [result_row(result) for result in results]
        elif week.state in {'live', 'finalizing'} and week.activated_at and now >= week.start_at and ready(week):
            try:
                scored = services.provisional_standings(week, now=now)
                entries = {entry.pk: entry for entry in week.entries.filter(state__in=['active', 'data_pending']).select_related('editor__selected_title', 'approved_application__selected_title')}
                for row in scored:
                    entry = entries.get(row['entry_id'])
                    if entry and not row.get('disqualified'):
                        # Scoring rows contain model instances and private audit fields.
                        # Publish the display contract only; placement comes from scoring.
                        pending = bool(row.get('data_pending'))
                        rows.append({
                            'entry_id': entry.pk, 'editor_id': entry.editor_id,
                            'username': entry.editor.username, 'video_url': entry.canonical_url,
                            'rank': None if pending else row.get('placement'), 'points': None,
                            'projected_points': None if pending else services.placement_points(week.scoring_version.config, row.get('placement')),
                            'state': 'data_pending' if pending else entry.state, 'data_pending': pending,
                            **{key: row.get(key) for key in ('weekly_score', 'response_score', 'improvement_score', 'popularity_score', 'last_refresh')},
                            **score_metadata(week.scoring_version.config, row),
                            **entry_identity(entry),
                        })
            except ValueError:
                pass
        state = week.state
        if not frozen and now >= week.cutoff_at:
            state = 'finalizing'
        metadata = week_data(week)
        return JsonResponse({'period': period, 'period_label': metadata['label'], 'state': state,
                             'provisional': not frozen, 'rows': rows, 'result_revision': week.current_revision,
                             'minimum_entries': week.scoring_version.config.get('minimum_entries'),
                             'last_refresh': metadata['last_refresh']})
    award = None
    if period == 'all_time':
        rows = [dict(row) for row in services.aggregate_standings()]
    else:
        year = int(request.GET.get('year', now.year))
        month = int(request.GET.get('month', now.month))
        if not 2000 <= year <= 2200 or not 1 <= month <= 12:
            return JsonResponse({'error': 'Invalid standings period.'}, status=400)
        award = MonthlyAward.objects.filter(year=year, month=month, effective=True).first()
        rows = [dict(row) for row in services.monthly_standings(year, month)]
    entry_ids = [entry_id for row in rows for entry_id in row['entry_ids']]
    latest = {}
    for result in WeeklyResult.objects.filter(entry_id__in=entry_ids, revision=F('week__current_revision')).select_related('entry__editor__selected_title', 'entry__approved_application__selected_title', 'week').order_by('-week__start_at', '-pk'):
        latest.setdefault(result.entry.editor_id, result)
    for row in rows:
        result = latest.get(row['editor_id'])
        row.update(username=result.entry.editor.username if result else 'Former editor', scored_rounds=len(row['entry_ids']), latest_result=None, rank_change=None)
        if result:
            row.update(entry_identity(result.entry))
            row.update(video_url=result.entry.canonical_url, entry_id=result.entry_id)
            row['latest_result'] = {'rank': result.placement, 'points': result.league_points,
                                    'period_label': f'{result.week.start_at:%d %b} – {result.week.cutoff_at - timedelta(days=1):%d %b %Y}'}
    if period == 'all_time':
        return JsonResponse({'period': period, 'period_label': 'All-time league points', 'state': 'accumulating',
            'provisional': False, 'rows': rows})
    label = f'{year}-{month:02d}'
    return JsonResponse({'period': period, 'period_label': label,
        'state': 'finalized' if award else ('finalizing' if (year, month) < (now.year, now.month) else 'accumulating'),
        'provisional': not bool(award), 'rows': rows})


def winner_data(entry, points, score, label):
    return {'editor_id': entry.editor_id, 'username': entry.editor.username, 'entry_id': entry.pk,
            **title_data(entry.editor, entry.approved_application),
            'title': entry.title, 'video_url': entry.canonical_url, 'platform': entry.platform, 'video_format': entry.video_format,
            'period_label': label, 'points': points, 'weekly_score': score}


@endpoint()
def winners(request):
    weekly = None
    # Only the effective finalized revision may produce a public winner.
    for week in CompetitionWeek.objects.filter(state='finalized').select_related('scoring_version').order_by('-start_at')[:20]:
        if not ready(week):
            continue
        result = WeeklyResult.objects.filter(week=week, revision=week.current_revision, is_winner=True).select_related('entry__editor__selected_title', 'entry__approved_application__selected_title').first()
        if result:
            weekly = winner_data(result.entry, result.league_points, result.weekly_score, week_data(week)['label'])
            break
    monthly = None
    award = MonthlyAward.objects.filter(effective=True, editor__isnull=False, entry__isnull=False).select_related('entry__editor__selected_title', 'entry__approved_application__selected_title', 'entry__week__scoring_version').order_by('-year', '-month').first()
    if award and award.entry.week.state == 'finalized' and ready(award.entry.week):
        result = WeeklyResult.objects.filter(entry=award.entry, revision=award.entry.week.current_revision, placement__isnull=False).first()
        if result:
            monthly = {**winner_data(award.entry, award.points, result.weekly_score, f'{award.year}-{award.month:02d}'),
                       'award_title': 'Editor of the Month', 'representative_edit': True}
    now = timezone.now()
    current, _ = selected_weeks(now)
    previous_month = now.date().replace(day=1) - timedelta(days=1)
    previous_final = MonthlyAward.objects.filter(year=previous_month.year, month=previous_month.month, effective=True).exists()
    previous_scheduled = CompetitionWeek.objects.filter(scoring_date__year=previous_month.year, scoring_date__month=previous_month.month).exists()
    return JsonResponse({'weekly_winner': weekly, 'monthly_winner': monthly,
        'weekly_state': ('finalizing' if current and now >= current.cutoff_at and current.state not in services.FINAL_STATES else current.state) if current else 'scheduled',
        'monthly_state': 'finalized' if previous_final else ('finalizing' if previous_scheduled else 'scheduled')})


def entry_data(entry, now):
    unlocked = bool(entry.state == 'queued'
                    and entry.week.state == 'scheduled' and now < entry.week.start_at)
    result = WeeklyResult.objects.filter(entry=entry, revision=entry.week.current_revision).select_related('baseline', 'snapshot').first()
    data = {'id': entry.pk, 'title': entry.title, 'video_url': entry.canonical_url, 'platform': entry.platform,
            'state': entry.state, 'week': week_data(entry.week),
            'can_replace': bool(unlocked and league_enabled() and ready(entry.week)
                                and entry.week.start_at == next_week_start(now)),
            'can_withdraw': unlocked, 'approved_application_id': entry.approved_application_id,
            'validation_message': '', 'last_refresh': None, 'points': None}
    if result and entry.week.state == 'finalized' and ready(entry.week) and result.placement is not None:
        data.update({key: value for key, value in result_row(result).items() if key not in {'rank', 'username', 'video_url'}})
        data['state'] = 'finalized'
    elif entry.week.state in {'live', 'finalizing'} and entry.week.activated_at and ready(entry.week):
        if now >= entry.week.cutoff_at and entry.state in {'active', 'data_pending'}:
            data['state'] = 'finalizing'
        try:
            row = next((row for row in services.provisional_standings(entry.week, now=now) if row['entry_id'] == entry.pk), None)
            if row and not row.get('disqualified'):
                data.update({key: row.get(key) for key in ('weekly_score', 'response_score', 'improvement_score', 'popularity_score', 'last_refresh')})
                data.update(score_metadata(entry.week.scoring_version.config, row))
                if row.get('data_pending'):
                    data['state'] = 'data_pending'
        except ValueError:
            data['state'] = 'data_pending'
    return data


@endpoint(authenticated=True)
def own_entries(request):
    entries = CompetitionEntry.objects.filter(editor=request.user).select_related('editor', 'approved_application', 'week__scoring_version').order_by('-week__start_at', '-pk')[:50]
    applications = list(EditorApplication.objects.filter(user=request.user).order_by('-applied_date', '-pk'))
    channels = [item for item in applications if item.status == 'accepted' and item.channel_verified and not item.removal_requested]
    return JsonResponse({'entries': [entry_data(entry, timezone.now()) for entry in entries],
                         'channel_applications': [{'id': item.pk, 'platform': item.channel_type, 'channel_name': item.channel_name,
                             'status': item.status, 'channel_verified': item.channel_verified, 'removal_requested': item.removal_requested,
                             'url': f'/applications/editors/{item.pk}'} for item in applications],
                         'verified_channels': [{'id': item.pk, 'platform': item.channel_type, 'channel_name': item.channel_name,
                                                'channel_url': item.channel_link} for item in channels]})


def prepare_intake(request, data):
    application = get_object_or_404(EditorApplication, pk=data.get('approved_application_id'), user=request.user,
                                    status='accepted', channel_verified=True, removal_requested=False)
    video_url = data.get('video_url', '')
    if not isinstance(video_url, str) or len(video_url) > 1000:
        raise ValueError('Enter a supported video URL.')
    return application, fetch_verified_video(application, video_url)


def assert_open(week, now):
    if not league_enabled() or not ready(week):
        raise ProviderSetupRequired('League entries are not open yet.')
    if week.state != 'scheduled' or now >= week.start_at or week.start_at != next_week_start(now):
        raise ValueError('This round is locked. Only next-week entries can be changed.')


def assert_calibrated_observation(week, data):
    config = week.scoring_version.config
    supported = f"{data['platform']}:{data['video_format']}"
    if supported not in config['supported_formats']:
        raise ProviderSetupRequired('This video format is not supported by this round’s rules. Please contact the league administrator.')
    band = age_band(config, (week.cutoff_at - data['published_at']).total_seconds())
    if not is_cohort(config) and f'{supported}:{band}' not in config['references']:
        raise ProviderSetupRequired('This video needs an age-matched scoring reference before it can enter the league.')


def save_entry(request, week, application, data):
    # Preserve database uniqueness for canonical IDs and one editor/round even
    # when two requests race. The client cannot supply content keys or scores.
    entry = CompetitionEntry.objects.create(
        week=week, editor=request.user, approved_application=application,
        platform=data['platform'], video_id=data['video_id'], channel_id=data['channel_id'],
        video_format=data['video_format'], published_at=data['published_at'],
        canonical_url=data['canonical_url'], title=data.get('title', '')[:200],
        content_key=data.get('content_key') or f"{data['platform']}:{data['video_id']}", state='queued',
    )
    services.record_snapshot(entry, data)
    return entry


def intake_response(request, replacing=None):
    if limited(request, 'league_intake', limit=10, period=600, identity=str(request.user.pk)):
        return JsonResponse({'error': 'Too many entry attempts. Please try again later.'}, status=429)
    data = payload(request)
    now = timezone.now()
    week = get_object_or_404(CompetitionWeek.objects.select_related('scoring_version'), start_at=next_week_start(now))
    try:
        assert_open(week, now)
        application, observation = prepare_intake(request, data)
        channel_identity = (application.channel_type, application.channel_link)
        # Provider I/O occurs before locking; recheck deadline and channel rights after it.
        with transaction.atomic():
            week = CompetitionWeek.objects.select_for_update().select_related('scoring_version').get(pk=week.pk)
            assert_open(week, timezone.now())
            application = get_object_or_404(EditorApplication.objects.select_for_update(), pk=application.pk, user=request.user,
                                            status='accepted', channel_verified=True, removal_requested=False)
            if channel_identity != (application.channel_type, application.channel_link):
                raise ProviderSetupRequired('Your approved channel changed during validation. Please try again.')
            assert_calibrated_observation(week, observation)
            if replacing:
                old = get_object_or_404(CompetitionEntry.objects.select_for_update(), pk=replacing, editor=request.user, week=week)
                if old.state != 'queued':
                    raise ValueError('Only queued entries can be replaced.')
                old.state = 'withdrawn'
                old.save(update_fields=['state'])
            entry = save_entry(request, week, application, observation)
        return JsonResponse({'entry': entry_data(entry, timezone.now())}, status=201)
    except ProviderSetupRequired as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except Http404:
        raise
    except ProviderError as exc:
        status_code = 503 if exc.retryable else (409 if exc.code in {'not_configured', 'authorization_required', 'identity_required'} else 400)
        return JsonResponse({'error': str(exc)}, status=status_code)
    except IntegrityError:
        return JsonResponse({'error': 'You already have an entry for this round, or this edit has already been entered for this competition month. Choose a different edit or wait for a round in the next month.'}, status=409)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception as exc:
        logger.warning('League intake failed (%s)', type(exc).__name__)
        return JsonResponse({'error': 'Video validation is temporarily unavailable. Your entry was not changed.'}, status=503)


@endpoint(('POST',), authenticated=True)
def submit_entry(request):
    return intake_response(request)


@endpoint(('POST',), authenticated=True)
def replace_entry(request, entry_id):
    get_object_or_404(CompetitionEntry, pk=entry_id, editor=request.user)
    return intake_response(request, replacing=entry_id)


@endpoint(('POST',), authenticated=True)
def withdraw_entry(request, entry_id):
    payload(request)
    entry = get_object_or_404(CompetitionEntry.objects.select_related('week'), pk=entry_id, editor=request.user)
    with transaction.atomic():
        week = CompetitionWeek.objects.select_for_update().get(pk=entry.week_id)
        entry = CompetitionEntry.objects.select_for_update().get(pk=entry_id, editor=request.user)
        if entry.state != 'queued' or week.state != 'scheduled' or timezone.now() >= week.start_at:
            return JsonResponse({'error': 'The entry is locked and cannot be withdrawn.'}, status=409)
        entry.state = 'withdrawn'
        entry.save(update_fields=['state'])
    return JsonResponse({'message': 'Your queued entry was withdrawn.'})
