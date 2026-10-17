"""Turn committed official league revisions into idempotent member updates.

The event row is created inside the scoring transaction, so worker recovery does
not depend on an on-commit callback surviving process interruption. Historical
rows are never scanned to manufacture new events or retroactive email consent.
"""
from django.db import transaction
from django.utils import timezone
from edithub.league_models import WeeklyRevision, MonthlyAward, LeaguePointsAward, CompetitionWeek, LeagueSeason
from .manager import notification_manager
from .models import LeagueNotificationEvent, Notification, MemberActivityDelivery, NotificationPreference


def _notify(event, user, suffix, title, message, kind, related, *, email=True):
    return notification_manager.create_notification(user, title, message, kind,
        related_object=related, event_key=f'league:{event.event_key}:{suffix}:{user.pk}',
        send_channels=None if event.email_eligible and email else ['in_app'])


def _first_lead(user, key, title, message, related):
    """Caller holds the week/season lock; the unique event key survives retries."""
    if Notification.objects.filter(event_key=key).exists():
        return None
    return notification_manager.create_notification(user, title, message, 'league_ranking',
        related_object=related, event_key=key, send_channels=['in_app'])


def _email_lead(notice, *, eligible=True, combined_result=None):
    if notice is None or not eligible:
        return
    # One frozen-result email can contain the milestone. If result emails are
    # disabled but ranking emails are enabled, the milestone still stands alone.
    if combined_result and MemberActivityDelivery.objects.filter(notification=combined_result).exists():
        return
    from .activity_email import queue_activity_email
    preferences, _ = NotificationPreference.objects.get_or_create(user=notice.user)
    queue_activity_email(notice, preferences)


@transaction.atomic
def notify_provisional_leader(week_id, now=None):
    """Called after a collection pass, never from public page reads.

    Require a complete eligible cohort so a partially collected provider batch
    cannot falsely announce its first fetched entry as the leader.
    """
    from edithub.league.services import provisional_standings
    from edithub.league.scoring import version_ready
    now = now or timezone.now()
    week = CompetitionWeek.objects.select_for_update().select_related('scoring_version').filter(pk=week_id).first()
    if (not week or week.state != 'live' or week.current_revision
            or not week.start_at <= now < week.cutoff_at or not version_ready(week.scoring_version)):
        return False
    rows = provisional_standings(week, now=now)
    eligible = [row for row in rows if not row.get('disqualified')]
    if (any(row.get('data_pending') for row in eligible)
            or len(eligible) < week.scoring_version.config['minimum_entries']):
        return False
    leader = next((row for row in eligible if row.get('placement') == 1), None)
    if not leader:
        return False
    notice = _first_lead(leader['entry'].editor,
        f'league:weekly-lead:{week.pk}:{leader["editor_id"]}', 'You are leading this week',
        f'You reached provisional #1 in the round ending {week.scoring_date:%d %B %Y}. '
        'Standings can change until points are frozen; this is not a winner announcement.', week)
    _email_lead(notice)
    return notice is not None


def _weekly(event):
    revision = WeeklyRevision.objects.select_related('week__scoring_version').filter(pk=event.object_id).first()
    if revision is None or revision.number != revision.week.current_revision:
        return
    week = revision.week
    official = revision.state == 'finalized'
    version = week.scoring_version
    from edithub.league.scoring import version_ready
    if official and not version_ready(version):
        return
    label = f'round ending {week.scoring_date:%d %B %Y}'
    prefix = 'Corrected ' if revision.number > 1 else ''
    # Unsent superseded result emails are replaced by the correction email.
    old_ids = week.revisions.exclude(pk=revision.pk).values_list('pk', flat=True)
    for pk in old_ids:
        MemberActivityDelivery.objects.filter(notification__event_key__startswith=f'league:weekly:{pk}:',
            status__in=['pending', 'failed']).update(status='cancelled', last_error='Superseded by an official correction.', updated_at=timezone.now())
    MemberActivityDelivery.objects.filter(notification__event_key__startswith=f'league:weekly-lead:{week.pk}:',
        status__in=['pending', 'failed']).update(status='cancelled', last_error='Provisional round has finished.', updated_at=timezone.now())
    # Serialize all weeks of this year when recording monthly first-lead markers.
    LeagueSeason.objects.select_for_update().get(year=week.scoring_date.year)
    from edithub.league.services import monthly_standings
    standings = {row['editor_id']: row for row in monthly_standings(week.scoring_date.year, week.scoring_date.month)}
    leads = {}
    if official:
        from django.contrib.auth import get_user_model
        for standing in standings.values():
            if standing['rank'] != 1:
                continue
            member = get_user_model().objects.get(pk=standing['editor_id'])
            key = f'league:monthly-lead:{week.scoring_date:%Y-%m}:{member.pk}'
            leads[member.pk] = _first_lead(member, key, 'You are leading the monthly league',
                f'You reached #1 in the {week.scoring_date:%B %Y} monthly league with {standing["points"]} points. '
                'The Editor of the Month title is awarded after the month is finalized.', week)
    delivered_results = {}
    results = week.results.filter(revision=revision.number).select_related('entry__editor')
    for result in results:
        member = result.entry.editor
        if revision.state == 'canceled':
            message = f'The {label} was canceled. No official points or weekly winner are awarded.'
        elif not official:
            message = f'The {label} is an exhibition round. Results are available, with no official league points or weekly winner.'
        elif result.placement is None:
            message = f'Your entry in the {label} has no official placement and receives 0 league points. Check the result details.'
        else:
            message = f'You finished #{result.placement} in the {label}, earning {result.league_points} league points. Your weekly score is {result.weekly_score}.'
        if official:
            message += ' These weekly points are frozen.'
            if result.is_winner:
                message += ' You won Edit of the Week; your edit is featured on the website.'
            if leads.get(member.pk):
                message += f' You have also reached #1 in the {week.scoring_date:%B %Y} monthly league.'
        delivered_results[member.pk] = _notify(event, member, 'result', f'{prefix}league result'.capitalize(),
            message, 'league_result', week, email=official or revision.number > 1)
        if official and result.is_winner:
            _notify(event, member, 'winner', f'{prefix}weekly league winner'.capitalize(),
                f'You are the official first-place winner of the {label}. Your edit is featured in the league showcase.', 'league_award', week, email=False)

    for member_id, notice in leads.items():
        _email_lead(notice, eligible=event.email_eligible, combined_result=delivered_results.get(member_id))

    # Changes can affect editors who did not enter this particular week, too.
    from django.contrib.auth import get_user_model
    members = LeaguePointsAward.objects.filter(week__scoring_date__year=week.scoring_date.year, week__scoring_date__month=week.scoring_date.month).values_list('editor_id', flat=True).distinct()
    for member in get_user_model().objects.filter(pk__in=members):
        standing = standings.get(member.pk)
        message = (f'Your {week.scoring_date:%B %Y} monthly league standing is #{standing["rank"]} with {standing["points"]} points.'
                   if standing else f'You have no official ranking in the {week.scoring_date:%B %Y} monthly league yet.')
        previous = Notification.objects.filter(user=member, notification_type='league_ranking').order_by('-created_at', '-pk').first()
        if previous is None or previous.message != message:
            _notify(event, member, 'standing', 'League standing updated', message, 'league_ranking', week, email=False)


def _period(event):
    if event.kind != 'monthly':
        return  # Preserve historical annual records without generating new alerts.
    model = MonthlyAward
    award = model.objects.select_related('editor').filter(pk=event.object_id, effective=True).first()
    if not award:
        return
    selector = {'year': award.year, 'month': award.month}
    label = f'{award.year}-{award.month:02d} monthly league'
    prefix = 'Corrected ' if award.revision > 1 else ''
    if award.editor_id:
        _notify(event, award.editor, 'winner', f'{prefix}Editor of the Month · {award.year}-{award.month:02d}',
            f'You are the official winner of the {label}, with {award.points} league points.', 'league_award', award)
    if award.revision > 1:
        previous = model.objects.filter(**selector, revision__lt=award.revision).order_by('-revision').select_related('editor').first()
        if previous and previous.editor_id and previous.editor_id != award.editor_id:
            _notify(event, previous.editor, 'corrected', 'League award corrected',
                f'The {label} award was corrected after a result review. Your earlier winner status has changed. Check the official results.', 'league_award', award)
        for previous in model.objects.filter(**selector, revision__lt=award.revision):
            MemberActivityDelivery.objects.filter(notification__event_key__startswith=f'league:{event.kind}:{previous.pk}:',
                status__in=['pending', 'failed']).update(status='cancelled', last_error='Superseded by an official correction.', updated_at=timezone.now())


@transaction.atomic
def process_league_event(event_id):
    event = LeagueNotificationEvent.objects.select_for_update().filter(pk=event_id, processed_at=None).first()
    if not event:
        return False
    if event.kind == 'weekly':
        _weekly(event)
    else:
        _period(event)
    event.processed_at = timezone.now()
    event.save(update_fields=['processed_at'])
    return True


def process_pending_league_events(limit=100):
    count = 0
    for pk in list(LeagueNotificationEvent.objects.filter(processed_at=None).order_by('pk').values_list('pk', flat=True)[:limit]):
        count += int(process_league_event(pk))
    return count
