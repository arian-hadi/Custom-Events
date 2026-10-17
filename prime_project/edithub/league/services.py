"""Transactional league operations. Call from explicit jobs, never model-save timers."""
import hashlib
import json
import secrets
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from django.db import transaction
from django.db.models import F, Max, OuterRef, Q, Subquery
from django.utils import timezone

from edithub.league_models import (CompetitionEntry, CompetitionWeek, EntryBaseline, LeaguePointsAward,
    LeagueSeason, MetricSnapshot, MonthlyAward, ScoringVersion, WeeklyResult, WeeklyRevision)
from .calendar import UTC, friday_date, month_end, utc, week_cutoff
from .scoring import CalibrationRequired, DataPending, LeagueError, age_band, decimal, is_cohort, score, score_cohort, validate_config, version_ready


FINAL_STATES = {"finalized", "exhibition", "canceled"}


def _now(value):
    return utc(value or timezone.now())


@transaction.atomic
def ensure_week(start, scoring_version):
    start = utc(start)
    cutoff = week_cutoff(start)
    friday = friday_date(start)
    season, _ = LeagueSeason.objects.get_or_create(year=friday.year)
    season = LeagueSeason.objects.select_for_update().get(pk=season.pk)
    week, created = CompetitionWeek.objects.get_or_create(start_at=start, defaults={
        "cutoff_at": cutoff, "scoring_date": friday, "season": season, "scoring_version": scoring_version,
    })
    if created and MonthlyAward.objects.filter(year=friday.year, month=friday.month, effective=True).exists():
        raise LeagueError("A finalized month cannot receive new rounds.")
    if week.scoring_version_id != scoring_version.pk:
        raise LeagueError("This round already has a different scoring version.")
    return week


def _freeze_version(version, now):
    version = ScoringVersion.objects.select_for_update().get(pk=version.pk)
    if not version_ready(version):
        raise CalibrationRequired("Official scoring requires confirmed rules and documented pilot calibration.")
    validate_config(version.config)
    if not version.frozen_at:
        version.frozen_at = now
        version.save(update_fields=["frozen_at"])
    return version


def _freeze_baseline(entry, config, available_at, frozen_at):
    if config.get('baseline_policy') == 'website_last_five_v1':
        return _freeze_website_baseline(entry, config, available_at, frozen_at)
    target_age = (entry.week.cutoff_at - entry.published_at).total_seconds()
    band = age_band(config, target_age)
    excluded = set(CompetitionEntry.objects.filter(editor=entry.editor, state="disqualified", platform=entry.platform).values_list("video_id", flat=True))
    excluded.add(entry.video_id)
    observations = MetricSnapshot.objects.filter(
        editor=entry.editor, platform=entry.platform, video_format=entry.video_format,
        status="success", completed_at__lte=available_at, received_at__lte=available_at,
        likes__isnull=False, views__isnull=False,
    ).exclude(video_id__in=excluded)
    selected = {}
    for observation in observations:
        observed_age = (observation.completed_at - observation.published_at).total_seconds()
        if observed_age < 0 or age_band(config, observed_age) != band:
            continue
        key = (abs(observed_age - target_age), observation.completed_at, observation.pk)
        if observation.video_id not in selected or key < selected[observation.video_id][0]:
            selected[observation.video_id] = (key, observation)
    samples = sorted((row[1] for row in selected.values()), key=lambda row: (row.published_at, row.video_id), reverse=True)[:config["baseline_max_samples"]]
    median = None
    if len(samples) >= config["baseline_min_samples"]:
        likes = sorted(Decimal(row.likes) for row in samples)
        middle = len(likes) // 2
        median = likes[middle] if len(likes) % 2 else (likes[middle - 1] + likes[middle]) / 2
    entry.age_band = band
    entry.save(update_fields=["age_band"])
    return EntryBaseline.objects.create(entry=entry, sample_ids=[row.pk for row in samples], sample_count=len(samples),
        median_likes=None if median is None else str(median), age_band=band,
        reason="insufficient_comparable_history" if median is None else "age_matched_creator_median",
        frozen_at=frozen_at)


def _freeze_website_baseline(entry, config, available_at, frozen_at):
    """Use only result revisions that existed before this round started.

    Saved source IDs preserve the comparison even after later corrections.
    Scored exhibitions count as experience, but confer no league points.
    """
    prior_participation = CompetitionEntry.objects.filter(editor=entry.editor,
        week__start_at__lt=entry.week.start_at, week__activated_at__isnull=False,
    ).filter(~Q(state='withdrawn') | Q(baseline__isnull=False)).exists()
    as_of_revision = WeeklyRevision.objects.filter(week_id=OuterRef('week_id'),
        created_at__lte=available_at).order_by('-number').values('number')[:1]
    results = WeeklyResult.objects.filter(entry__editor=entry.editor, week__cutoff_at__lte=available_at,
        revision=Subquery(as_of_revision), placement__isnull=False,
        snapshot__status='success', snapshot__likes__isnull=False, snapshot__views__isnull=False,
        snapshot__received_at__lte=available_at, snapshot__completed_at__lt=F('week__cutoff_at'),
    ).select_related('entry', 'snapshot').order_by('-week__start_at', '-pk')
    samples, seen_videos, seen_content = [], {(entry.platform, entry.video_id)}, {entry.content_key}
    for result in results:
        sample, previous = result.snapshot, result.entry
        identity = (previous.platform, previous.video_id)
        if (result.details.get('disqualified') or identity in seen_videos
                or (previous.content_key and previous.content_key in seen_content)
                or sample.entry_id != previous.pk or sample.editor_id != entry.editor_id
                or (sample.platform, sample.video_id) != identity
                or sample.channel_id != previous.channel_id
                or (sample.views == 0 and sample.likes > 0)):
            continue
        samples.append(result)
        seen_videos.add(identity)
        seen_content.add(previous.content_key)
        if len(samples) == config['baseline_max_samples']:
            break
    median = None
    if samples:
        likes = sorted(Decimal(result.snapshot.likes) for result in samples)
        middle = len(likes) // 2
        median = likes[middle] if len(likes) % 2 else (likes[middle - 1] + likes[middle]) / 2
    is_debut = not prior_participation
    band = age_band(config, (entry.week.cutoff_at - entry.published_at).total_seconds())
    entry.age_band = band
    entry.save(update_fields=['age_band'])
    return EntryBaseline.objects.create(entry=entry, sample_ids=[row.snapshot_id for row in samples],
        source_result_ids=[row.pk for row in samples], sample_count=len(samples),
        median_likes=None if median is None else str(median), age_band=band, is_debut=is_debut,
        reason='debut_week' if is_debut else ('website_result_median' if samples else 'no_valid_website_history'),
        frozen_at=frozen_at)


@transaction.atomic
def activate_week(week, now=None):
    now = _now(now)
    week = CompetitionWeek.objects.select_for_update().select_related("scoring_version").get(pk=week.pk)
    if week.activated_at or week.state in FINAL_STATES:
        return week
    if not week.start_at <= now < week.cutoff_at:
        raise LeagueError("Activation requires the open Monday–Friday scoring window.")
    version = _freeze_version(week.scoring_version, now)
    config = version.config
    entries = list(week.entries.select_for_update().exclude(state__in=["withdrawn", "disqualified"]))
    for entry in entries:
        band = age_band(config, (week.cutoff_at - entry.published_at).total_seconds())
        if not is_cohort(config) and f"{entry.platform}:{entry.video_format}:{band}" not in config["references"]:
            raise CalibrationRequired("An entry's platform, format and age require calibration before activation.")
        _freeze_baseline(entry, config, week.start_at, now)
        entry.state = "active"
        entry.save(update_fields=["state"])
    week.activated_at, week.state, week.data_status = now, "live", "pending"
    week.tie_seed = secrets.token_hex(32)
    week.save(update_fields=["activated_at", "state", "data_status", "tie_seed"])
    LeagueSeason.objects.filter(pk=week.season_id, state="scheduled").update(state="active")
    return week


def _snapshot_data(data, metadata):
    now = timezone.now()
    completed = utc(data["completed_at"])
    requested = utc(data.get("requested_at", completed))
    if requested > completed or completed > now + timedelta(seconds=5):
        raise LeagueError("Snapshot timestamps must describe a completed request.")
    status = data.get("status", "success")
    if status not in {"success", "error", "unavailable"}:
        raise LeagueError("Unknown metric collection outcome.")
    likes, views = data.get("likes"), data.get("views")
    for value in (likes, views):
        if value is not None and (type(value) is not int or not 0 <= value <= 9223372036854775807):
            raise LeagueError("Counters must be nonnegative integers, or missing.")
    if status == "success" and (likes is None or views is None):
        raise DataPending("A successful observation requires both lifetime counters.")
    provenance = dict(data.get("provenance") or {})
    if not data.get("provider"):
        raise LeagueError("Snapshot provider provenance is required.")
    # Received time is server-controlled. Callers cannot backfill purported historical access.
    return {**metadata, "requested_at": requested, "completed_at": completed, "received_at": now,
            "likes": likes, "views": views, "status": status, "provider": data["provider"], "provenance": provenance}


def record_snapshot(entry, data):
    metadata = {name: getattr(entry, name) for name in ("editor", "platform", "video_id", "channel_id", "video_format", "published_at")}
    for name in ("platform", "video_id", "channel_id", "video_format", "published_at"):
        if name in data and data[name] != metadata[name]:
            raise LeagueError("Provider identity does not match this entry.")
    values = _snapshot_data(data, metadata)
    prior = entry.snapshots.filter(status="success").order_by("-completed_at", "-pk").first()
    if prior and values["status"] == "success" and (values["likes"] < prior.likes or values["views"] < prior.views):
        values["provenance"]["counter_decrease"] = True
    return MetricSnapshot.objects.create(entry=entry, **values)


def record_comparison_snapshot(editor, data):
    metadata = {name: data[name] for name in ("platform", "video_id", "channel_id", "video_format", "published_at")}
    metadata["editor"] = editor
    metadata["published_at"] = utc(metadata["published_at"])
    return MetricSnapshot.objects.create(**_snapshot_data(data, metadata))


def _closing_snapshot(entry, week, now, final=False, override=None):
    candidates = entry.snapshots.filter(status="success", likes__isnull=False, views__isnull=False,
        completed_at__lt=week.cutoff_at, completed_at__lte=now, received_at__lte=now,
        platform=entry.platform, video_id=entry.video_id, channel_id=entry.channel_id,
        video_format=entry.video_format)
    if final:
        candidates = candidates.filter(completed_at__gte=week.cutoff_at - timedelta(seconds=week.scoring_version.config["cutoff_max_age_seconds"]))
    if override is not None:
        candidates = candidates.filter(pk=override)
    return candidates.order_by("-completed_at", "-pk").first()


def _draw(seed, identity):
    return hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest()


def _score_rows(week, now, final=False, snapshot_overrides=None, disqualified_entry_ids=None):
    overrides = {int(key): value for key, value in (snapshot_overrides or {}).items()}
    disqualified = set(disqualified_entry_ids or [])
    rows = []
    cohort = {}
    debut_ids = set()
    automatic = is_cohort(week.scoring_version.config)
    for entry in week.entries.select_related("editor").exclude(state="withdrawn"):
        # Initial scoring uses live moderation state. A correction supplies the
        # effective revision's complete decision set, which can also reinstate
        # an entry without mutating the historical entry or older result.
        excluded = entry.state == "disqualified" if disqualified_entry_ids is None else entry.pk in disqualified
        row = {"entry_id": entry.pk, "editor_id": entry.editor_id, "entry": entry,
               "data_pending": False, "disqualified": excluded}
        if row["disqualified"]:
            row.update({"placement": None, "league_points": 0})
            rows.append(row)
            continue
        try:
            baseline = entry.baseline
        except EntryBaseline.DoesNotExist:
            row["data_pending"] = True
            row["reason"] = "The round has not activated and frozen comparison history."
            rows.append(row)
            continue
        snapshot = _closing_snapshot(entry, week, now, final, overrides.get(entry.pk))
        if not snapshot:
            row["data_pending"], row["reason"] = True, "A valid metric observation is unavailable."
            rows.append(row)
            continue
        if automatic:
            if snapshot.views == 0 and snapshot.likes > 0:
                row.update(data_pending=True, reason='Inconsistent provider likes/views.')
                rows.append(row)
                continue
            cohort[entry.pk] = (snapshot.likes, snapshot.views, baseline.median_likes)
            if baseline.is_debut:
                debut_ids.add(entry.pk)
            values = {}
        else:
            values = score(week.scoring_version.config, f"{entry.platform}:{entry.video_format}:{entry.age_band}",
                           snapshot.likes, snapshot.views, baseline.median_likes)
        row.update(values)
        row.update({"snapshot_id": snapshot.pk, "baseline_id": baseline.pk, "last_refresh": snapshot.completed_at,
                    "baseline_sample_count": baseline.sample_count, "baseline_median_likes": baseline.median_likes,
                    "baseline_policy": week.scoring_version.config.get('baseline_policy', 'channel_age_matched'),
                    "tie_draw": _draw(week.tie_seed, entry.pk)})
        rows.append(row)
    if automatic:
        scores = score_cohort(week.scoring_version.config, cohort, debut_ids=debut_ids)
        for row in rows:
            if row['entry_id'] in scores:
                row.update(scores[row['entry_id']])
    ready = sorted((row for row in rows if not row["data_pending"] and not row["disqualified"]),
        # Unary minus rounds Decimal values to the ambient context (normally 28
        # digits). copy_negate preserves the full versioned scoring precision.
        key=lambda row: (decimal(row["weekly_score"]).copy_negate(), decimal(row["response_score"]).copy_negate(), decimal(row["improvement_score"]).copy_negate(), row["tie_draw"]))
    for placement, row in enumerate(ready, 1):
        row["placement"] = placement
    return ready + [row for row in rows if row["data_pending"] or row["disqualified"]]


def provisional_standings(week, now=None):
    week = CompetitionWeek.objects.select_related("scoring_version").get(pk=week.pk)
    if week.current_revision:
        return [{"entry_id": result.entry_id, "editor_id": result.entry.editor_id, "entry": result.entry,
                 "weekly_score": result.weekly_score, "response_score": result.response_score,
                 "improvement_score": result.improvement_score, "popularity_score": result.popularity_score,
                 "placement": result.placement, "league_points": result.league_points, "is_winner": result.is_winner,
                 "data_pending": False, "disqualified": result.details.get("disqualified", False), "details": result.details,
                 "revision": result.revision} for result in week.results.filter(revision=week.current_revision).select_related("entry")]
    return _score_rows(week, _now(now), final=_now(now) >= week.cutoff_at)


def placement_points(config, placement):
    """Versioned placement schedule, shared by projections and final awards."""
    if placement is None:
        return None
    return config["placement_points"][placement - 1] if placement <= len(config["placement_points"]) else config["finisher_points"]


def _write_revision(week, now, rows, *, state, reason="", actor=None):
    number = week.current_revision + 1
    config = week.scoring_version.config
    revision = WeeklyRevision.objects.create(week=week, number=number, state=state, reason=reason, actor=actor,
        created_at=now, config_digest=hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
    LeaguePointsAward.objects.filter(week=week, effective=True).update(effective=False)
    for row in rows:
        placement = row.get("placement")
        points = 0
        if state == "finalized" and placement is not None:
            points = placement_points(config, placement)
        details = {key: value for key, value in row.items() if key not in {"entry", "last_refresh"}}
        if row.get("last_refresh"):
            details["last_refresh"] = row["last_refresh"].isoformat()
        WeeklyResult.objects.create(week=week, entry_id=row["entry_id"], revision=number,
            snapshot_id=row.get("snapshot_id"), baseline_id=row.get("baseline_id"),
            **{name: row.get(name, "0") for name in ("response_score", "improvement_score", "popularity_score", "weekly_score")},
            placement=placement, league_points=points, is_winner=state == "finalized" and placement == 1, details=details)
        LeaguePointsAward.objects.create(week=week, entry_id=row["entry_id"], editor_id=row["editor_id"], revision=number, points=points)
    week.state, week.finalized_at, week.current_revision, week.data_status = state, now, number, "complete"
    week.save(update_fields=["state", "finalized_at", "current_revision", "data_status"])
    return revision


@transaction.atomic
def finalize_week(week, now=None):
    now = _now(now)
    week = CompetitionWeek.objects.select_for_update().select_related("scoring_version").get(pk=week.pk)
    if week.current_revision:
        return week.revisions.get(number=week.current_revision)
    if now < week.cutoff_at:
        raise LeagueError("The scoring window has not closed.")
    if not week.activated_at:
        raise DataPending("The round was not activated; its baselines cannot be reconstructed after cutoff.")
    _freeze_version(week.scoring_version, now)
    rows = _score_rows(week, now, final=True)
    if any(row["data_pending"] for row in rows):
        # Caller may expose data_pending. Raising rolls back and never publishes a partial result.
        raise DataPending("Closing metrics are missing; use an audited exception or cancel the round.")
    count = sum(not row["disqualified"] for row in rows)
    state = "finalized" if count >= week.scoring_version.config["minimum_entries"] else "exhibition"
    return _write_revision(week, now, rows, state=state)


def _authorize_correction(actor, reason):
    if not actor or not actor.is_active or not actor.is_staff or not (actor.is_superuser or actor.has_perm("edithub.change_competitionweek")):
        raise LeagueError("An authorized league administrator is required.")
    if not reason or not reason.strip():
        raise LeagueError("An audit reason is required.")


@transaction.atomic
def correct_week(week, *, reason, actor, snapshot_overrides=None, disqualified_entry_ids=None, now=None):
    _authorize_correction(actor, reason)
    now = _now(now)
    week = CompetitionWeek.objects.select_for_update().select_related("scoring_version").get(pk=week.pk)
    if not week.current_revision or week.state == "canceled":
        raise LeagueError("Only a completed scored round can be corrected.")
    entry_ids = set(week.entries.values_list("pk", flat=True))
    if not set(map(int, (snapshot_overrides or {}))).issubset(entry_ids) or not set(disqualified_entry_ids or []).issubset(entry_ids):
        raise LeagueError("Corrections must refer to entries in this round.")
    # Preserve each original closing snapshot unless this explicit correction replaces it.
    overrides = {result.entry_id: result.snapshot_id for result in week.results.filter(revision=week.current_revision) if result.snapshot_id}
    overrides.update(snapshot_overrides or {})
    prior_disqualified = {result.entry_id for result in week.results.filter(revision=week.current_revision) if result.details.get("disqualified")}
    disqualified = prior_disqualified if disqualified_entry_ids is None else set(disqualified_entry_ids)
    rows = _score_rows(week, now, final=True, snapshot_overrides=overrides, disqualified_entry_ids=disqualified)
    if any(row["data_pending"] for row in rows):
        raise DataPending("A correction cannot invent missing closing metrics.")
    count = sum(not row["disqualified"] for row in rows)
    revision = _write_revision(week, now, rows, state="finalized" if count >= week.scoring_version.config["minimum_entries"] else "exhibition", reason=reason, actor=actor)
    _refresh_dependent_awards(week, now, reason)
    return revision


@transaction.atomic
def cancel_week(week, *, reason, actor, now=None):
    _authorize_correction(actor, reason)
    now = _now(now)
    week = CompetitionWeek.objects.select_for_update().select_related("scoring_version").get(pk=week.pk)
    if week.state == "canceled":
        return week.revisions.get(number=week.current_revision)
    rows = [{"entry_id": entry.pk, "editor_id": entry.editor_id, "placement": None, "disqualified": True, "reason": reason}
            for entry in week.entries.exclude(state="withdrawn")]
    revision = _write_revision(week, now, rows, state="canceled", reason=reason, actor=actor)
    _refresh_dependent_awards(week, now, reason)
    return revision


def _aggregate_results(year=None, month=None):
    awards = LeaguePointsAward.objects.filter(effective=True,
        week__state="finalized", revision=F("week__current_revision")).select_related("entry", "week__scoring_version")
    if year is not None:
        awards = awards.filter(week__scoring_date__year=year)
    if month is not None:
        awards = awards.filter(week__scoring_date__month=month)
    # The same aggregate is used by standings, awards and the member overview.
    # Load effective results once rather than issuing one query for every award.
    result_query = WeeklyResult.objects.filter(week__state="finalized", revision=F("week__current_revision")).select_related("entry", "week")
    if year is not None:
        result_query = result_query.filter(week__scoring_date__year=year)
    if month is not None:
        result_query = result_query.filter(week__scoring_date__month=month)
    effective_results = {(result.entry_id, result.revision): result for result in result_query}
    rows, results, configurations = {}, [], {}
    with localcontext() as context:
        context.prec = 64
        for award in awards:
            version = award.week.scoring_version
            if version.pk not in configurations:
                try:
                    configurations[version.pk] = version_ready(version)
                except ValueError:
                    configurations[version.pk] = False
            if not configurations[version.pk]:
                continue
            result = effective_results.get((award.entry_id, award.revision))
            if result is None or result.placement is None:
                continue
            results.append(result)
            row = rows.setdefault(award.editor_id, {"editor_id": award.editor_id, "points": 0, "placements": Counter(), "weekly_score_total": Decimal(0), "entry_ids": []})
            row["points"] += award.points
            row["placements"][result.placement] += 1
            row["weekly_score_total"] += decimal(result.weekly_score)
            row["entry_ids"].append(award.entry_id)
    return rows, results


def aggregate_standings(year=None, month=None, *, tie_seed=None):
    rows, _ = _aggregate_results(year, month)
    max_place = max((max(row["placements"], default=0) for row in rows.values()), default=0)
    # A period draw is recorded only at finalization. Provisional exact ties share rank.
    def key(row):
        return (-row["points"], tuple(-row["placements"].get(place, 0) for place in range(1, max_place + 1)), row["weekly_score_total"].copy_negate())
    ordered = sorted(rows.values(), key=lambda row: (key(row), _draw(tie_seed, row["editor_id"]) if tie_seed else row["editor_id"]))
    previous, rank = None, 0
    for index, row in enumerate(ordered, 1):
        current = key(row)
        if current != previous or tie_seed:
            rank = index
        previous = current
        row.update({"rank": rank, "tie_draw": _draw(tie_seed, row["editor_id"]) if tie_seed else None,
                    "weekly_score_total": str(row["weekly_score_total"]), "placements": dict(row["placements"])})
    return ordered


def _period_award(model, year, month, now, reason="", force=False):
    if model is not MonthlyAward or month is None:
        raise LeagueError("Annual competition is retired. Finalize calendar months instead.")
    season = LeagueSeason.objects.select_for_update().filter(year=year).first()
    if season is None:
        raise LeagueError("No rounds have been scheduled for this calendar year.")
    boundary = month_end(year, month)
    if now < boundary:
        raise LeagueError("This award period has not ended.")
    selector = {"year": year, "month": month}
    previous = model.objects.filter(**selector, effective=True).first()
    if previous and not force:
        return previous
    weeks = CompetitionWeek.objects.filter(scoring_date__year=year, scoring_date__month=month)
    if weeks.exclude(state__in=FINAL_STATES).exists():
        raise DataPending("Every included round must be finalized or canceled first.")
    seed = previous.details["tie_seed"] if previous else secrets.token_hex(32)
    standings = aggregate_standings(year, month, tie_seed=seed)
    winner = standings[0] if standings else None
    representative = None
    if winner:
        _, results = _aggregate_results(year, month)
        candidates = [result for result in results if result.entry.editor_id == winner["editor_id"]]
        representative = sorted(candidates, key=lambda result: (decimal(result.weekly_score).copy_negate(), decimal(result.response_score).copy_negate(), result.week.start_at, result.entry_id))[0].entry
    revision = (model.objects.filter(**selector).aggregate(value=Max("revision"))["value"] or 0) + 1
    model.objects.filter(**selector, effective=True).update(effective=False)
    award = model.objects.create(**selector, revision=revision, editor_id=winner["editor_id"] if winner else None,
        entry=representative, points=winner["points"] if winner else 0, created_at=now,
        details={"tie_seed": seed, "standings": standings, "reason": reason,
                 "week_revisions": {str(week.pk): week.current_revision for week in weeks}, "empty": winner is None})
    return award


@transaction.atomic
def finalize_month(year, month, now=None):
    if not 1 <= month <= 12:
        raise LeagueError("Invalid month.")
    return _period_award(MonthlyAward, year, month, _now(now))


@transaction.atomic
def finalize_season(year, now=None):
    raise LeagueError("Annual competition is retired. Finalize calendar months instead.")


def _refresh_dependent_awards(week, now, reason):
    year, month = week.scoring_date.year, week.scoring_date.month
    if MonthlyAward.objects.filter(year=year, month=month, effective=True).exists():
        _period_award(MonthlyAward, year, month, now, reason=reason, force=True)


def monthly_standings(year, month):
    """Use the persisted tie decision for a finalized month, otherwise accumulate."""
    award = MonthlyAward.objects.filter(year=year, month=month, effective=True).first()
    return award.details.get('standings', []) if award else aggregate_standings(year, month)
