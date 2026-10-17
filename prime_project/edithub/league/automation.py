"""Recurring round preparation. Never backfill elapsed weeks or rewrite rules."""
import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from edithub.league_models import CompetitionWeek, LeagueSettings, ScoringVersion
from .calendar import next_week_start
from .scoring import automatic_config, LeagueError


def league_enabled():
    configured = LeagueSettings.objects.filter(pk=1).values_list('enabled', flat=True).first()
    return bool(getattr(settings, 'LEAGUE_ENABLED', False)) if configured is None else configured


@transaction.atomic
def prepare_rounds(now=None):
    """Keep four future Mondays ready. Lock settings to serialize concurrent ticks."""
    from .services import ensure_week
    if not league_enabled():
        return []
    options, _ = LeagueSettings.objects.get_or_create(pk=1, defaults={'enabled': True})
    options = LeagueSettings.objects.select_for_update().get(pk=options.pk)
    if not options.enabled:
        return []
    version = automatic_version(options, now=now)
    start = next_week_start(now or timezone.now())
    prepared = []
    for offset in range(4):
        date = start + timedelta(weeks=offset)
        existing = CompetitionWeek.objects.filter(start_at=date).first()
        # Existing manual, entered and historical rounds keep their original version.
        prepared.append(existing or ensure_week(date, version))
    return prepared


def automatic_version(options, *, now=None):
    config = automatic_config()
    config['weights'] = {key: str(Decimal(getattr(options, field)) / 100) for key, field in (
        ('response', 'response_weight'), ('improvement', 'improvement_weight'), ('popularity', 'popularity_weight'))}
    config.update(placement_points=options.placement_points, finisher_points=options.finisher_points,
        minimum_entries=options.minimum_entries, debut_improvement_score=str(options.debut_improvement_score))
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:24]
    version, _ = ScoringVersion.objects.get_or_create(name=f'automatic-{digest}', defaults={
        'config': config, 'rules_confirmed': True, 'calibrated': False, 'frozen_at': now or timezone.now(),
        'calibration_notes': 'Automatic within-round comparison. Initial policy, not pilot-validated. No historical metrics or reference distributions were fabricated.',
    })
    return version


@transaction.atomic
def upgrade_scheduled_grading(week, *, actor, reason, now=None):
    """Explicit, audited rollout. Never regrade a live or historical round."""
    from django.contrib.admin.models import LogEntry, CHANGE
    from django.contrib.contenttypes.models import ContentType
    now = now or timezone.now()
    if not actor or not actor.is_active or not actor.is_staff or not actor.has_perm('edithub.change_competitionweek') or not reason or not reason.strip():
        raise LeagueError('A permitted administrator and audit reason are required.')
    week = CompetitionWeek.objects.select_for_update().get(pk=week.pk)
    if week.state != 'scheduled' or week.activated_at or week.current_revision or week.start_at <= now:
        raise LeagueError('Only future, unstarted rounds can adopt new grading rules.')
    options = LeagueSettings.objects.select_for_update().get(pk=1)
    version = automatic_version(options, now=now)
    if version.pk == week.scoring_version_id:
        return week
    previous = week.scoring_version_id
    week.scoring_version = version
    week.save(update_fields=['scoring_version'])
    LogEntry.objects.log_action(user_id=actor.pk, content_type_id=ContentType.objects.get_for_model(week).pk,
        object_id=week.pk, object_repr=str(week), action_flag=CHANGE,
        change_message=f'Grading version {previous} → {version.pk}. {reason.strip()}')
    return week
