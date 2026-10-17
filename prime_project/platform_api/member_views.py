"""Private member overview assembled from existing website and league records."""

from edithub.league.automation import league_enabled
from edithub.league.scoring import version_ready
import re
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.db.models import Count, F, Min, Q, Sum
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from edithub.league import services
from edithub.league_models import CompetitionEntry, LeagueSeason, ScoringVersion, WeeklyResult
from edithub.league.scoring import validate_config
from edithub.models import EditorApplication, EditSubmission
from events.models import EventApplication
from notifications.models import Notification
from shop.amazon import catalog_queryset
from shop.models import PaymentOrder
from shop.payments import order_data

from .league_views import ready, selected_weeks, week_data
from .views import endpoint, image_url, notification_data
from .member_titles import selected_editor_title


def editor_application_data(application, platform):
    if application is None:
        return {"id": None, "platform": platform, "status": "not_applied", "channel_name": "",
                "channel_verified": False, "removal_requested": False, "applied_at": None,
                "updated_at": None, "url": f"/editing-hub/apply?platform={platform}"}
    return {"id": application.pk, "platform": platform, "status": application.status,
            "channel_name": application.channel_name, "channel_verified": application.channel_verified,
            "removal_requested": application.removal_requested, "applied_at": application.applied_date,
            "updated_at": application.updated_date,
            "url": f"/applications/editors/{application.pk}"}


def member_data(user, applications):
    accepted = applications.filter(status="accepted", removal_requested=False)
    preferred = accepted.filter(channel_type=user.profile_channel_source).first() if user.profile_channel_source else None
    primary = preferred or accepted.first()
    channel_display = user.profile_display_mode == "channel" and primary is not None
    title = selected_editor_title(user, primary)
    verified = list(accepted.filter(channel_verified=True).order_by("channel_type").values_list("channel_type", flat=True).distinct())
    return {
        "id": user.pk, "username": user.username,
        "display_name": (primary.channel_name or user.username) if channel_display else user.username,
        "profile_picture": image_url(user.profile_picture) or (primary.channel_thumbnail or None if channel_display else None),
        "editor_title": title.name if title else ("Editor" if primary else "Community member"),
        "editor_title_rarity": title.rarity if title else None,
        "verified_editor": bool(verified), "verified_platforms": verified,
    }


def standing_data(rows, user_id):
    own = next((row for row in rows if row["editor_id"] == user_id), None)
    return {"rank": own["rank"] if own else None, "points": own["points"] if own else 0,
            "scored_rounds": len(own["entry_ids"]) if own else 0}


def brief_entry(entry):
    return {"id": entry.pk, "title": entry.title, "state": entry.state,
            "video_url": entry.canonical_url, "detail_url": f"/editing-hub#entry-{entry.pk}"} if entry else None


def official_results(user):
    # Never show an obsolete correction, an exhibition result, or a live estimate
    # as the member's official rank or league points.
    valid_versions = []
    for version in ScoringVersion.objects.filter(rules_confirmed=True):
        try:
            if version_ready(version):
                valid_versions.append(version.pk)
        except ValueError:
            continue
    return WeeklyResult.objects.filter(entry__editor=user, week__state="finalized",
        revision=F("week__current_revision"), placement__isnull=False,
        week__scoring_version_id__in=valid_versions
    ).select_related("entry", "week__scoring_version")


def result_data(result):
    if result is None or not ready(result.week):
        return None
    return {"entry_id": result.entry_id, "title": result.entry.title, "rank": result.placement,
            "points": result.league_points, "weekly_score": result.weekly_score,
            "period_label": week_data(result.week)["label"], "scored_at": result.week.finalized_at,
            "video_url": result.entry.canonical_url}


def league_data(user, entries, results, now):
    current, upcoming = selected_weeks(now)
    enabled = league_enabled()
    configured = ready(upcoming or current)
    can_submit = bool(enabled and ready(upcoming) and upcoming.state == "scheduled" and now < upcoming.start_at)
    reason = "" if can_submit else (
        "The league is being prepared. Entries will open when the rules and scoring setup are ready."
        if not enabled or not configured else "Entry registration for the next round is not open yet."
    )
    return {
        "enabled": enabled, "configuration_ready": configured, "can_submit": can_submit, "reason": reason,
        "month": {"label": now.strftime("%B %Y"), **standing_data(services.monthly_standings(now.year, now.month), user.pk)},
        "current_week": week_data(current), "next_week": week_data(upcoming),
        # Entries close at the start of the round; cutoff_at is the metric cutoff.
        "submission_deadline": upcoming.start_at if upcoming else None,
        "current_entry": brief_entry(entries.filter(week=current).exclude(state="withdrawn").first()) if current else None,
        "next_entry": brief_entry(entries.filter(week=upcoming).exclude(state="withdrawn").first()) if upcoming else None,
        "latest_result": result_data(results.order_by("-week__start_at", "-pk").first()),
        "rank_change": None,
    }


def youtube_thumbnail(video_url, video_id=None):
    """Use a known YouTube thumbnail address; never scrape providers on page load."""
    if video_id is None:
        parsed = urlparse(video_url)
        if parsed.hostname in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            parts = parsed.path.strip("/").split("/")
            video_id = parts[1] if len(parts) == 2 and parts[0] in {"shorts", "embed"} else parse_qs(parsed.query).get("v", [""])[0]
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) else None


def latest_edit_data(entries, legacy, results):
    entry = entries.exclude(state="withdrawn").order_by("-created_at", "-pk").first()
    edit = legacy.order_by("-submitted_date", "-pk").first()
    if entry and (not edit or entry.created_at >= edit.submitted_date):
        result = results.filter(entry=entry).first()
        official = result_data(result)
        return {"id": entry.pk, "source": "league", "title": entry.title,
                "video_url": entry.canonical_url, "detail_url": f"/editing-hub#entry-{entry.pk}",
                "thumbnail": youtube_thumbnail(entry.canonical_url, entry.video_id) if entry.platform == "youtube" else None,
                "platform": entry.platform, "submitted_at": entry.created_at, "state": entry.state,
                "rank": official["rank"] if official else None,
                "league_points": official["points"] if official else None, "upvotes": None}
    if not edit:
        return None
    # The confirmation preview only accepts pending records. Completed archive
    # entries have an existing owner-only page; rejected work has no detail page.
    detail_url = (reverse("edithub:preview_edit_submission", args=[edit.pk]) if edit.status == "pending"
                  else reverse("edithub:edit_submission_success", args=[edit.pk]) if edit.status == "verified"
                  else edit.video_url)
    return {"id": edit.pk, "source": "legacy", "title": edit.title, "video_url": edit.video_url,
            "detail_url": detail_url,
            "thumbnail": youtube_thumbnail(edit.video_url) if edit.channel_type == "youtube" else None,
            "platform": edit.channel_type, "submitted_at": edit.submitted_date, "state": edit.status,
            "rank": None, "league_points": None, "upvotes": edit.upvote_count}


@endpoint(authenticated=True)
def dashboard(request):
    now, user = timezone.now(), request.user
    applications = EditorApplication.objects.filter(user=user).select_related("selected_title").order_by("-applied_date", "-pk")
    entries = CompetitionEntry.objects.filter(editor=user)
    legacy = EditSubmission.objects.filter(user=user)
    results = official_results(user)
    league = league_data(user, entries, results, now)
    old_stats = legacy.aggregate(total=Count("pk"), verified=Count("pk", filter=Q(status="verified")), upvotes=Sum("upvote_count"))
    league_stats = results.aggregate(points=Sum("league_points"), best=Min("placement"))
    events = EventApplication.objects.filter(applicant=user).select_related("event").order_by("-updated_date", "-pk")
    from notifications.announcement_inbox import member_notifications
    notices = member_notifications(user).order_by("-created_at", "-pk")
    # Legacy ranking notices describe follower positions. Keep the inbox count
    # truthful while the V2 overview only previews relevant member updates.
    preview_notices = notices.exclude(notification_type="ranking_updated")
    orders = PaymentOrder.objects.filter(user=user).order_by("-created_at", "-pk")[:3]
    return JsonResponse({
        "generated_at": now, "member": member_data(user, applications), "league": league,
        "latest_edit": latest_edit_data(entries, legacy, results),
        "edit_stats": {"league_submissions": entries.exclude(state="withdrawn").count(),
                       "legacy_submissions": old_stats["total"], "legacy_verified": old_stats["verified"],
                       "legacy_upvotes": old_stats["upvotes"] or 0,
                       "league_points": league_stats["points"], "best_league_result": league_stats["best"]},
        "applications": {
            "editors": [editor_application_data(application, platform) for platform in ("youtube", "tiktok")
                        if (application := applications.filter(channel_type=platform).first()) is not None],
            "events": [{"id": item.pk, "event_id": item.event_id, "title": item.event.title,
                        "status": item.status, "applied_at": item.applied_date, "updated_at": item.updated_date,
                        "url": f"/applications#event-{item.pk}"} for item in events[:3]],
            "event_count": events.count(),
        },
        "notifications": {"unread_count": notices.filter(is_read=False).count(),
            "results": [notification_data(item) for item in preview_notices[:4]]},
        "orders": [{**order_data(order), "url": f"/account/orders/{order.pk}"} for order in orders],
        "favorites_count": catalog_queryset(user.favorite_products.all()).count(),
    })
