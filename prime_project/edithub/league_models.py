"""Additive V2 league records. No legacy scoring signals use these models."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .league.scoring import default_config, validate_config


def initial_placement_points():
    return default_config()['placement_points']


class LeagueSettings(models.Model):
    """One operator-owned switch; edits affect only rounds not yet scheduled."""
    enabled = models.BooleanField(default=False, verbose_name='Open automatic league')
    response_weight = models.PositiveSmallIntegerField(default=50, verbose_name='Like-rate weight')
    improvement_weight = models.PositiveSmallIntegerField(default=30, verbose_name='Website performance weight')
    popularity_weight = models.PositiveSmallIntegerField(default=20, verbose_name='Total views weight')
    debut_improvement_score = models.PositiveSmallIntegerField(default=85,
        help_text='Performance component out of 100 in the first competition week only. 85 contributes 25.5 overall at a 30% weight; you may choose 90.')
    minimum_entries = models.PositiveSmallIntegerField(default=5)
    placement_points = models.JSONField(default=initial_placement_points)
    finisher_points = models.PositiveSmallIntegerField(default=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'League settings'
        verbose_name_plural = 'League settings'
        constraints = [models.CheckConstraint(check=Q(id=1), name='league_settings_singleton')]

    def clean(self):
        if self.response_weight + self.improvement_weight + self.popularity_weight != 100:
            raise ValidationError('The three score weights must total 100%.')
        if self.minimum_entries < 1:
            raise ValidationError('At least one eligible entry is required.')
        if self.debut_improvement_score > 100:
            raise ValidationError({'debut_improvement_score': 'Choose a score from 0 to 100.'})
        points = self.placement_points
        if not isinstance(points, list) or len(points) != 10 or any(type(value) is not int or value < 0 for value in points):
            raise ValidationError('Provide ten nonnegative placement awards.')
        if points != sorted(points, reverse=True) or self.finisher_points > points[-1]:
            raise ValidationError('Points must not increase for lower placements.')

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return 'Automatic monthly league'


class FrozenRecord(models.Model):
    """Service-created audit records cannot be edited through ordinary saves."""
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("This audit record is immutable; use a new result revision.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("League audit records cannot be deleted.")


class ScoringVersion(models.Model):
    name = models.SlugField(unique=True)
    config = models.JSONField(default=default_config)
    rules_confirmed = models.BooleanField(default=False)
    calibrated = models.BooleanField(default=False)
    calibration_notes = models.TextField(blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.calibrated:
            if not self.calibration_notes.strip():
                raise ValidationError("Describe and retain the real pilot calibration evidence.")
            try:
                validate_config(self.config)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()
            if original and original.frozen_at and any(getattr(original, field) != getattr(self, field) for field in ("name", "config", "rules_confirmed", "calibrated", "calibration_notes", "frozen_at")):
                raise ValidationError("An activated scoring version is immutable; create a new version.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class LeagueSeason(models.Model):
    year = models.PositiveSmallIntegerField(unique=True)
    state = models.CharField(max_length=16, default="scheduled", choices=[("scheduled", "Scheduled"), ("active", "Active"), ("finalized", "Finalized")])
    finalized_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.year)


class CompetitionWeek(models.Model):
    season = models.ForeignKey(LeagueSeason, on_delete=models.PROTECT, related_name="weeks")
    scoring_version = models.ForeignKey(ScoringVersion, on_delete=models.PROTECT, related_name="weeks")
    start_at = models.DateTimeField(unique=True)
    cutoff_at = models.DateTimeField()
    scoring_date = models.DateField(db_index=True)
    state = models.CharField(max_length=16, default="scheduled", choices=[(value, value.title()) for value in ("scheduled", "live", "finalizing", "finalized", "exhibition", "canceled")])
    activated_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    current_revision = models.PositiveIntegerField(default=0)
    tie_seed = models.CharField(max_length=64, blank=True, editable=False)
    data_status = models.CharField(max_length=32, default="pending")

    class Meta:
        ordering = ["-start_at"]

    def __str__(self):
        return f"Week of {self.start_at.date()}"


class CompetitionEntry(models.Model):
    week = models.ForeignKey(CompetitionWeek, on_delete=models.PROTECT, related_name="entries")
    competition_month = models.DateField(editable=False, help_text="First day of the month containing the competition's Friday cutoff.")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="league_entries")
    approved_application = models.ForeignKey("edithub.EditorApplication", on_delete=models.PROTECT, null=True, blank=True, related_name="league_entries")
    platform = models.CharField(max_length=16, choices=[("youtube", "YouTube"), ("tiktok", "TikTok")])
    video_id = models.CharField(max_length=128)
    channel_id = models.CharField(max_length=128)
    video_format = models.CharField(max_length=32, default="unknown")
    published_at = models.DateTimeField()
    canonical_url = models.URLField(max_length=500)
    title = models.CharField(max_length=300, blank=True)
    content_key = models.CharField(max_length=255)
    state = models.CharField(max_length=16, default="queued", choices=[(value, value.replace("_", " ").title()) for value in ("queued", "active", "withdrawn", "disqualified", "data_pending")])
    age_band = models.CharField(max_length=32, blank=True, editable=False)
    moderation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["editor", "week"], condition=~Q(state="withdrawn"), name="league_one_editor_per_week"),
            models.UniqueConstraint(fields=["competition_month", "platform", "video_id"], condition=~Q(state="withdrawn"), name="league_video_once_per_month"),
            models.UniqueConstraint(fields=["competition_month", "content_key"], condition=~Q(state="withdrawn"), name="league_edit_once_per_month"),
        ]

    def save(self, *args, **kwargs):
        # Derive the scope on the server; the submission date and client input
        # cannot move an edit into a different month's duplicate allowance.
        self.competition_month = self.week.scoring_date.replace(day=1)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"competition_month"}
        if not self.content_key:
            self.content_key = f"{self.platform}:{self.video_id}"
        if self.pk:
            previous = type(self).objects.select_related("week").get(pk=self.pk)
            immutable = ("week_id", "competition_month", "editor_id", "approved_application_id", "platform", "video_id", "channel_id", "video_format", "published_at", "canonical_url", "content_key", "age_band")
            if previous.week.activated_at and any(getattr(previous, name) != getattr(self, name) for name in immutable):
                raise ValidationError("Activated entry identity and baseline age are immutable.")
            if previous.week.current_revision and (self.state != previous.state or self.moderation_reason != previous.moderation_reason):
                raise ValidationError("Use an audited correction to change a finalized entry.")
        super().save(*args, **kwargs)


class MetricSnapshot(FrozenRecord):
    entry = models.ForeignKey(CompetitionEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="snapshots")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="league_metric_snapshots")
    platform = models.CharField(max_length=16)
    video_id = models.CharField(max_length=128)
    channel_id = models.CharField(max_length=128)
    video_format = models.CharField(max_length=32)
    published_at = models.DateTimeField()
    requested_at = models.DateTimeField()
    completed_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(default=timezone.now, editable=False)
    likes = models.PositiveBigIntegerField(null=True, blank=True)
    views = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=[("success", "Success"), ("error", "Error"), ("unavailable", "Unavailable")])
    provider = models.CharField(max_length=64)
    provenance = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["editor", "platform", "video_format", "completed_at"], name="league_baseline_observation")]
        ordering = ["completed_at", "pk"]


class LeagueHistorySync(models.Model):
    """Hourly comparison-history collection state; never a scoring observation."""
    application = models.OneToOneField("edithub.EditorApplication", on_delete=models.PROTECT, related_name="league_history_sync")
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="pending", choices=[(value, value.title()) for value in ("pending", "running", "success", "partial", "unavailable")])
    observations = models.PositiveSmallIntegerField(default=0)
    failures = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    # Discovery resumes across hourly batches so older eligible edits are not
    # permanently hidden behind the newest uploads. No counters live here.
    next_cursor = models.JSONField(null=True, blank=True)
    pending_video_ids = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Channel application {self.application_id}: {self.status}"


class EntryBaseline(FrozenRecord):
    source_result_ids = models.JSONField(default=list, blank=True)
    is_debut = models.BooleanField(default=False)
    entry = models.OneToOneField(CompetitionEntry, on_delete=models.PROTECT, related_name="baseline")
    sample_ids = models.JSONField(default=list)
    sample_count = models.PositiveSmallIntegerField(default=0)
    median_likes = models.CharField(max_length=100, null=True, blank=True)
    age_band = models.CharField(max_length=32)
    reason = models.CharField(max_length=100)
    frozen_at = models.DateTimeField()


class WeeklyRevision(FrozenRecord):
    week = models.ForeignKey(CompetitionWeek, on_delete=models.PROTECT, related_name="revisions")
    number = models.PositiveIntegerField()
    state = models.CharField(max_length=16)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    config_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["week", "number"], name="league_week_revision")]


class WeeklyResult(FrozenRecord):
    week = models.ForeignKey(CompetitionWeek, on_delete=models.PROTECT, related_name="results")
    entry = models.ForeignKey(CompetitionEntry, on_delete=models.PROTECT, related_name="results")
    revision = models.PositiveIntegerField()
    snapshot = models.ForeignKey(MetricSnapshot, null=True, on_delete=models.PROTECT)
    baseline = models.ForeignKey(EntryBaseline, null=True, on_delete=models.PROTECT)
    # Decimal strings avoid backend-dependent SQLite floating-point coercion.
    response_score = models.CharField(max_length=100, default="0")
    improvement_score = models.CharField(max_length=100, default="0")
    popularity_score = models.CharField(max_length=100, default="0")
    weekly_score = models.CharField(max_length=100, default="0")
    placement = models.PositiveIntegerField(null=True)
    league_points = models.PositiveIntegerField(default=0)
    is_winner = models.BooleanField(default=False)
    details = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["entry", "revision"], name="league_entry_result_revision")]
        ordering = ["placement", "pk"]


class LeaguePointsAward(FrozenRecord):
    week = models.ForeignKey(CompetitionWeek, on_delete=models.PROTECT, related_name="points_awards")
    entry = models.ForeignKey(CompetitionEntry, on_delete=models.PROTECT, related_name="points_awards")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="league_points_awards")
    revision = models.PositiveIntegerField()
    points = models.PositiveIntegerField()
    effective = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entry", "revision"], name="league_points_revision"),
            models.UniqueConstraint(fields=["entry"], condition=Q(effective=True), name="league_effective_entry_points"),
        ]


class MonthlyAward(FrozenRecord):
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    revision = models.PositiveIntegerField()
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="league_monthly_awards")
    entry = models.ForeignKey(CompetitionEntry, null=True, on_delete=models.PROTECT, related_name="monthly_awards")
    points = models.PositiveIntegerField(default=0)
    effective = models.BooleanField(default=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["year", "month", "revision"], name="league_month_award_revision"),
                       models.UniqueConstraint(fields=["year", "month"], condition=Q(effective=True), name="league_effective_month_award")]


class SeasonAward(FrozenRecord):
    year = models.PositiveSmallIntegerField()
    revision = models.PositiveIntegerField()
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="league_season_awards")
    entry = models.ForeignKey(CompetitionEntry, null=True, on_delete=models.PROTECT, related_name="season_awards")
    points = models.PositiveIntegerField(default=0)
    effective = models.BooleanField(default=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["year", "revision"], name="league_season_award_revision"),
                       models.UniqueConstraint(fields=["year"], condition=Q(effective=True), name="league_effective_season_award")]
