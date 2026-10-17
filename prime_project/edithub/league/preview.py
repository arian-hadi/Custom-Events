"""Read-only visual fixtures, deliberately separate from competition services."""
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core import signing
from django.utils import timezone

from .calendar import next_week_start

SALT = 'edithub.local-visual-preview.v1'
MAX_AGE = 7200
STATES = ('live', 'frozen', 'pending')


def preview_enabled():
    return bool(settings.DEBUG and urlsplit(getattr(settings, 'V2_FRONTEND_URL', '')).hostname in {'localhost', '127.0.0.1', '::1'})


def issue_token():
    return signing.dumps({'purpose': 'league-visual-preview'}, salt=SALT)


def valid_token(token):
    try:
        return signing.loads(token, salt=SALT, max_age=MAX_AGE) == {'purpose': 'league-visual-preview'}
    except (signing.BadSignature, ValueError, TypeError):
        return False


def sample_league(state, now=None):
    """No ORM, provider calls, jobs, emails, votes, or points writes."""
    start = next_week_start(now or timezone.now())
    cutoff = start + timedelta(days=5)
    simulated = start + timedelta(days=2, hours=12) if state == 'live' else cutoff + timedelta(hours=12)
    month = (cutoff - timedelta(days=1)).date().replace(day=1)
    previous_month = month - timedelta(days=1)
    frozen = state == 'frozen'
    label = f'{start:%d %b} – {cutoff - timedelta(days=1):%d %b %Y}'
    names = ['Demo Prime', 'Demo Bumblebee', 'Demo Arcee', 'Demo Mirage', 'Demo Jazz', 'Demo Ironhide']
    awards = [25, 20, 16, 13, 11, 10]
    earlier_points = [45, 40, 30, 25, 20, 10]
    rows = []
    monthly = []
    for index, name in enumerate(names):
        missing = state == 'pending' and index == 5
        row = dict(editor_id=index + 1, entry_id=index + 1, username=name, channel_name='Sample creator',
            platform='youtube' if index % 2 == 0 else 'tiktok', channel_verified=True, video_url='',
            rank=None if missing else index + 1, points=awards[index] if frozen else None,
            projected_points=None if missing or frozen else awards[index],
            weekly_score=None if missing else str(83 - index * 10),
            response_score=None if missing else str(90 - index * 10),
            improvement_score=None if missing else str(80 - index * 10),
            popularity_score=None if missing else str(70 - index * 10),
            state='data_pending' if missing else 'finalized' if frozen else 'active', data_pending=missing, neutral_baseline=False)
        rows.append(row)
        monthly.append(dict(editor_id=index + 1, username=name, channel_name='Sample creator',
            platform=row['platform'], rank=index + 1, points=earlier_points[index] + (awards[index] if frozen else 0),
            scored_rounds=3 if frozen else 2, channel_verified=True))
    winner = dict(username=names[0], title='Sample Transformers edit', video_url='', points=25,
        weekly_score='83', period_label=label if frozen else 'Previous week · sample result')
    return {
        'preview': True, 'state': state, 'simulated_at': simulated, 'week_label': label,
        'starts_at': start, 'cutoff_at': cutoff, 'month_label': month.strftime('%B %Y'),
        'weekly': dict(period='week', period_label=label, state='finalized' if frozen else 'finalizing' if state == 'pending' else 'live',
            provisional=not frozen, rows=rows, last_refresh=simulated, result_revision=1 if frozen else 0),
        'monthly': dict(period='month', period_label=month.strftime('%B %Y'), state='accumulating', provisional=True, rows=monthly),
        'all_time': dict(period='all_time', period_label='All-time league points', state='accumulating', provisional=False,
            rows=[dict(row, points=row['points'] + 100, scored_rounds=row['scored_rounds'] + 8) for row in monthly]),
        'weekly_winner': winner,
        'monthly_winner': dict(winner, points=72, period_label=previous_month.strftime('%B %Y') + ' · sample result'),
    }
