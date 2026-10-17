"""League operations and audit pages. All state changes use league services."""
from datetime import datetime, time, timedelta

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .league import services
from .league.calendar import UTC
from .league.scoring import is_cohort, validate_config, version_ready
from .league.automation import league_enabled, prepare_rounds, upgrade_scheduled_grading
from .league_models import (
    CompetitionEntry, CompetitionWeek, EntryBaseline, LeaguePointsAward,
    LeagueHistorySync, LeagueSeason, LeagueSettings, MetricSnapshot, MonthlyAward, ScoringVersion, SeasonAward,
    WeeklyResult, WeeklyRevision,
)


def configuration_status(version):
    if not version:
        return "Save a draft, then supply documented pilot calibration."
    try:
        validate_config(version.config)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        return f"Not ready: {exc}"
    if not version.rules_confirmed:
        return "Rules must be confirmed before activation."
    if is_cohort(version.config):
        return "Automatic starter rules ready. Compares real entries within each round; not pilot-validated."
    if not version.calibrated or not version.calibration_notes.strip():
        return "Document and confirm real pilot calibration before activation."
    return "Ready for activation during the UTC scoring window."


class LeagueSettingsForm(forms.ModelForm):
    for index in range(1, 11):
        locals()[f'place_{index}'] = forms.IntegerField(min_value=0, label=f'Place {index} points')

    class Meta:
        model = LeagueSettings
        exclude = ('placement_points',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        points = self.instance.placement_points
        for index in range(10):
            self.fields[f'place_{index + 1}'] = forms.IntegerField(min_value=0, label=f'Place {index + 1} points', initial=points[index])

    def clean(self):
        cleaned = super().clean()
        values = [cleaned.get(f'place_{index + 1}') for index in range(10)]
        if all(value is not None for value in values):
            self.instance.placement_points = values
            if values != sorted(values, reverse=True) or cleaned.get('finisher_points', 0) > values[-1]:
                raise forms.ValidationError('Points must not increase for lower placements.')
        return cleaned


@admin.register(LeagueSettings)
class LeagueSettingsAdmin(admin.ModelAdmin):
    form = LeagueSettingsForm
    readonly_fields = ('operation_summary', 'updated_at')
    fieldsets = (
        ('Automatic competition', {'fields': ('enabled', 'operation_summary'), 'description':
            'Save once to open entries. The league worker keeps four upcoming weeks ready, scores Monday–Friday, freezes at Saturday 00:00 UTC and awards Editor of the Month automatically. No monthly registration or JSON setup.'}),
        ('Score weights (%)', {'fields': ('response_weight', 'improvement_weight', 'popularity_weight'), 'description':
            'Must total 100. Like rate (likes/views), performance against the last five finalized website edits, and total views. Scores compare real entries within each round; cross-platform fairness is not empirically validated. Missing provider metrics stay pending.'}),
        ('First competition week', {'fields': ('debut_improvement_score',), 'description':
            'A one-time performance component for debut editors, across all months and platforms. Returning editors with no usable history receive the neutral 50/100 component. This does not add extra league points.'}),
        ('League points', {'fields': tuple(f'place_{index}' for index in range(1, 11)) + ('finisher_points', 'minimum_entries'), 'description':
            'Changes apply only to rounds not yet scheduled. The next four weeks may already have locked rules. Smaller rounds are exhibitions. Past results and already scheduled rounds never change here.'}),
        ('Record', {'fields': ('updated_at',)}),
    )

    @admin.display(description='How it runs')
    def operation_summary(self, obj):
        return 'Approved editors submit one edit for the following week. Every qualifying weekly placement adds monthly points. YouTube uses your existing API key; TikTok requires the editor’s authorized provider connection. The scheduler must remain running.'

    def has_add_permission(self, request):
        return not LeagueSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        weeks = prepare_rounds()
        self.message_user(request, f'Saved. {len(weeks)} upcoming rounds ready. Existing results and round rules were preserved.')


class ScoringVersionForm(forms.ModelForm):
    class Meta:
        model = ScoringVersion
        fields = "__all__"

    def clean_config(self):
        config = self.cleaned_data["config"]
        if not isinstance(config, dict):
            raise forms.ValidationError("Configuration must be a JSON object.")
        for key, expected in (("weights", dict), ("references", dict), ("age_bands", list),
                              ("placement_points", list), ("supported_formats", list)):
            if key in config and not isinstance(config[key], expected):
                raise forms.ValidationError(f"Invalid {key} structure in configuration.")
        if any(not isinstance(band, dict) for band in config.get("age_bands", [])):
            raise forms.ValidationError("Every age band must be a JSON object.")
        if any(not isinstance(reference, dict) for reference in config.get("references", {}).values()):
            raise forms.ValidationError("Every calibration reference must be a JSON object.")
        return config

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("calibrated") and "config" in cleaned:
            try:
                validate_config(cleaned["config"])
            except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                self.add_error("config", f"Calibration is incomplete or malformed: {exc}")
                # Model validation runs after the form; do not pass malformed JSON
                # to it once the field has already been rejected.
                cleaned["calibrated"] = False
        return cleaned


@admin.register(ScoringVersion)
class ScoringVersionAdmin(admin.ModelAdmin):
    form = ScoringVersionForm
    change_form_template = 'admin/edithub/league_scoring_form.html'
    list_display = ("name", "rules_confirmed", "calibrated", "frozen_at", "readiness")
    list_filter = ("rules_confirmed", "calibrated")
    search_fields = ("name", "calibration_notes")
    readonly_fields = ("created_at", "frozen_at", "readiness")
    actions = None

    @admin.display(description="Readiness")
    def readiness(self, obj):
        return configuration_status(obj)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.frozen_at:
            return tuple(field.name for field in self.model._meta.fields) + ("readiness",)
        return self.readonly_fields

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.frozen_at) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


class LeagueAuditAdmin(admin.ModelAdmin):
    """No admin save, add, bulk edit or deletion may bypass immutable history."""
    actions = None
    list_per_page = 50

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ScheduleRoundsForm(forms.Form):
    scoring_version = forms.ModelChoiceField(queryset=ScoringVersion.objects.all().order_by("-created_at"))
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}),
                                help_text="Monday date. Each round starts at 00:00 UTC and closes Saturday at 00:00 UTC.")
    count = forms.IntegerField(min_value=1, max_value=53, initial=4, label="Number of weekly rounds")

    def clean_start_date(self):
        start = self.cleaned_data["start_date"]
        if start.weekday() != 0:
            raise forms.ValidationError("Choose a Monday. Round dates are always UTC.")
        return start


class RoundOperationForm(forms.Form):
    operation = forms.ChoiceField(choices=[("activate", "Activate and freeze rules / baselines"),
        ("finalize", "Finalize using valid closing metrics"), ("correct", "Create an audited result correction"),
        ("cancel", "Cancel this round with an audit reason"),
        ("upgrade_grading", "Apply current league settings to this future round")])
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}),
                             help_text="Required for corrections, cancellation and grading upgrades; retained in the audit log.")
    snapshot_overrides = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text='Corrections only. Entry ID to existing snapshot ID, for example {"12": 345}. Blank preserves original closing snapshots.')
    disqualified_entry_ids = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Corrections only. Complete list of disqualified entry IDs, for example [12, 13]. Blank preserves prior decisions; [] clears correction-based disqualifications.")

    def __init__(self, *args, week, **kwargs):
        self.week = week
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        operation = cleaned.get("operation")
        if operation in {"correct", "cancel", "upgrade_grading"} and not cleaned.get("reason", "").strip():
            self.add_error("reason", "An audit reason is required.")
        overrides = cleaned.get("snapshot_overrides")
        disqualified = cleaned.get("disqualified_entry_ids")
        if operation != "correct":
            if overrides is not None or disqualified is not None:
                self.add_error(None, "Snapshot replacements and disqualifications apply only to corrections.")
            return cleaned
        entry_ids = set(self.week.entries.exclude(state="withdrawn").values_list("pk", flat=True))
        if overrides is not None:
            if not isinstance(overrides, dict) or any(
                not isinstance(key, str) or not key.isascii() or not key.isdigit() or int(key) <= 0
                or type(value) is not int or value <= 0 for key, value in overrides.items()
            ):
                self.add_error("snapshot_overrides", "Use an object mapping positive entry IDs to positive snapshot IDs.")
            else:
                normalized = {int(key): value for key, value in overrides.items()}
                if len(normalized) != len(overrides) or not set(normalized).issubset(entry_ids):
                    self.add_error("snapshot_overrides", "Each entry must be unique and belong to this round.")
                else:
                    found = set(MetricSnapshot.objects.filter(pk__in=normalized.values(), status="success")
                                .values_list("entry_id", "pk"))
                    if any((entry, snapshot) not in found for entry, snapshot in normalized.items()):
                        self.add_error("snapshot_overrides", "Each replacement must be an existing successful snapshot belonging to its entry.")
                    else:
                        cleaned["snapshot_overrides"] = normalized
        if disqualified is not None and (not isinstance(disqualified, list) or any(
            type(value) is not int or value not in entry_ids for value in disqualified
        ) or len(set(disqualified)) != len(disqualified)):
            self.add_error("disqualified_entry_ids", "Use a list of unique entry IDs belonging to this round.")
        return cleaned


@admin.register(CompetitionWeek)
class CompetitionWeekAdmin(LeagueAuditAdmin):
    list_display = ("start_at", "cutoff_at", "scoring_version", "state", "data_status", "current_revision", "operations")
    list_filter = ("state", "data_status", "season", "scoring_version")
    date_hierarchy = "start_at"
    change_list_template = "admin/edithub/league_round_list.html"
    change_form_template = "admin/edithub/league_round_change.html"
    list_select_related = ("scoring_version", "season")

    def can_operate(self, request):
        return request.user.is_active and request.user.is_staff and request.user.has_perm("edithub.change_competitionweek")

    def get_urls(self):
        return [path("schedule/", self.admin_site.admin_view(self.schedule_view), name="edithub_competitionweek_schedule"),
                path("<int:object_id>/operations/", self.admin_site.admin_view(self.operations_view), name="edithub_competitionweek_operations")] + super().get_urls()

    @admin.display(description="Round details")
    def operations(self, obj):
        return format_html('<a href="{}">Readiness and operations</a>', reverse("admin:edithub_competitionweek_operations", args=[obj.pk]))

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "can_operate": self.can_operate(request)})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url,
            {**(extra_context or {}), "can_operate": self.can_operate(request)})

    def page(self, request, title, **context):
        return TemplateResponse(request, "admin/edithub/league_operation.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": title,
            "league_enabled": league_enabled(), **context,
        })

    def schedule_view(self, request):
        if not self.can_operate(request):
            raise PermissionDenied
        form = ScheduleRoundsForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    start = datetime.combine(form.cleaned_data["start_date"], time.min, tzinfo=UTC)
                    weeks = [services.ensure_week(start + timedelta(weeks=index), form.cleaned_data["scoring_version"])
                             for index in range(form.cleaned_data["count"])]
                    for week in weeks:
                        self.log_change(request, week, "Scheduled or verified weekly round through league service.")
            except (ValueError, ValidationError) as exc:
                form.add_error(None, str(exc))
            else:
                self.message_user(request, f"Scheduled or verified {len(weeks)} rounds. Draft rules must pass readiness before activation.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:edithub_competitionweek_changelist"))
        return self.page(request, "Schedule league rounds", form=form, submit_label="Schedule rounds")

    def operations_view(self, request, object_id):
        week = self.get_queryset(request).filter(pk=object_id).first()
        if not week:
            raise Http404
        if not self.has_view_permission(request, week):
            raise PermissionDenied
        can_operate = self.can_operate(request)
        if request.method == "POST" and not can_operate:
            raise PermissionDenied
        form = RoundOperationForm(request.POST or None, week=week)
        if request.method == "POST" and form.is_valid():
            operation = form.cleaned_data["operation"]
            try:
                with transaction.atomic():
                    if operation == "activate":
                        services.activate_week(week)
                    elif operation == "finalize":
                        services.finalize_week(week)
                    elif operation == "correct":
                        services.correct_week(week, actor=request.user, reason=form.cleaned_data["reason"],
                            snapshot_overrides=form.cleaned_data.get("snapshot_overrides"),
                            disqualified_entry_ids=form.cleaned_data.get("disqualified_entry_ids"))
                    elif operation == "cancel":
                        services.cancel_week(week, actor=request.user, reason=form.cleaned_data["reason"])
                    elif operation == "upgrade_grading":
                        upgrade_scheduled_grading(week, actor=request.user, reason=form.cleaned_data['reason'])
                    self.log_change(request, week, f"League operation: {operation}. {form.cleaned_data.get('reason', '')}")
            except (ValueError, ValidationError) as exc:
                form.add_error(None, str(exc))
            else:
                self.message_user(request, f"Round operation completed: {operation}.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:edithub_competitionweek_operations", args=[week.pk]))
        return self.page(request, f"League round: {week.start_at.date()}", week=week,
            readiness=configuration_status(week.scoring_version), can_operate=can_operate,
            form=form if can_operate else None, submit_label="Run selected operation",
            results=week.results.filter(revision=week.current_revision).select_related("entry__editor"),
            revisions=week.revisions.select_related("actor").order_by("-number"),
            snapshots_url=reverse("admin:edithub_metricsnapshot_changelist") + f"?entry__week__id__exact={week.pk}",
            entries_url=reverse("admin:edithub_competitionentry_changelist") + f"?week__id__exact={week.pk}")


@admin.register(LeagueSeason)
class LeagueSeasonAdmin(LeagueAuditAdmin):
    list_display = ("year", "state", "finalized_at")
    list_filter = ("state",)


@admin.register(CompetitionEntry)
class CompetitionEntryAdmin(LeagueAuditAdmin):
    list_display = ("id", "week", "editor", "title", "platform", "state", "age_band")
    list_filter = ("state", "platform", "week")
    search_fields = ("editor__username", "editor__email", "title", "video_id", "channel_id", "content_key")
    list_select_related = ("week", "editor")


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(LeagueAuditAdmin):
    list_display = ("id", "entry", "editor", "platform", "video_id", "status", "likes", "views", "completed_at", "received_at")
    list_filter = ("status", "platform", "provider", "entry__week")
    search_fields = ("video_id", "channel_id", "editor__username", "editor__email")
    list_select_related = ("entry", "editor")
    date_hierarchy = "completed_at"


@admin.register(EntryBaseline)
class EntryBaselineAdmin(LeagueAuditAdmin):
    list_display = ("id", "entry", "age_band", "sample_count", "median_likes", "reason", "frozen_at")
    list_filter = ("age_band", "reason")
    search_fields = ("entry__editor__username", "entry__video_id")
    list_select_related = ("entry",)


@admin.register(WeeklyRevision)
class WeeklyRevisionAdmin(LeagueAuditAdmin):
    list_display = ("week", "number", "state", "actor", "created_at")
    list_filter = ("state", "week")
    search_fields = ("reason", "actor__username")
    list_select_related = ("week", "actor")


@admin.register(WeeklyResult)
class WeeklyResultAdmin(LeagueAuditAdmin):
    list_display = ("week", "entry", "revision", "placement", "weekly_score", "league_points", "is_winner")
    list_filter = ("is_winner", "week")
    search_fields = ("entry__editor__username", "entry__video_id")
    list_select_related = ("week", "entry")


@admin.register(LeaguePointsAward)
class LeaguePointsAwardAdmin(LeagueAuditAdmin):
    list_display = ("editor", "week", "entry", "revision", "points", "effective")
    list_filter = ("effective", "week")
    search_fields = ("editor__username", "editor__email")
    list_select_related = ("editor", "week", "entry")


@admin.register(MonthlyAward)
class MonthlyAwardAdmin(LeagueAuditAdmin):
    list_display = ("year", "month", "editor", "points", "revision", "effective")
    list_filter = ("year", "month", "effective")
    search_fields = ("editor__username", "editor__email")
    list_select_related = ("editor",)


@admin.register(SeasonAward)
class SeasonAwardAdmin(LeagueAuditAdmin):
    list_display = ("year", "editor", "points", "revision", "effective")
    list_filter = ("year", "effective")
    search_fields = ("editor__username", "editor__email")
    list_select_related = ("editor",)


@admin.register(LeagueHistorySync)
class LeagueHistorySyncAdmin(LeagueAuditAdmin):
    list_display = ("application", "status", "last_started_at", "last_completed_at", "observations", "failures", "error_code")
    list_filter = ("status", "application__channel_type")
    search_fields = ("application__user__username", "application__user__email")
    list_select_related = ("application",)
