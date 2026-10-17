"""Bounded video discovery and caption preparation, with retry-safe records."""
from datetime import timedelta
import unicodedata

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.admin_email import queue_admin_alert
from .models import YouTubeBlogChannel, YouTubeBlogVideo, YouTubeBlogSuppression
from . import youtube_source as provider


def _title_key(title):
    return ' '.join(unicodedata.normalize('NFKC', title).casefold().split())


def save_video(channel, data, *, manual=False):
    defaults = {key: data.get(key) or (None if key == "published_at" else "")
                for key in ("title", "description", "published_at", "thumbnail_url")}
    defaults["title"] = defaults["title"][:200]
    with transaction.atomic():
        # Serialize manual and scheduled imports for this channel. Existing
        # records, including historical duplicates, are never rewritten.
        channel = YouTubeBlogChannel.objects.select_for_update().get(pk=channel.pk)
        title_key = _title_key(defaults["title"])
        suppressed = YouTubeBlogSuppression.objects.filter(channel=channel)
        matching = [pk for pk, video_id, title in suppressed.values_list("pk", "video_id", "title")
                    if video_id == data["video_id"] or _title_key(title) == title_key]
        if matching:
            if not manual:
                return None, False
            suppressed.filter(pk__in=matching).delete()
        existing = YouTubeBlogVideo.objects.filter(video_id=data["video_id"]).first()
        if existing:
            return existing, False
        for pk, title in channel.videos.values_list("pk", "title").iterator():
            if _title_key(title) == title_key:
                return YouTubeBlogVideo.objects.get(pk=pk), False
        video, created = YouTubeBlogVideo.objects.get_or_create(video_id=data["video_id"], defaults={"channel": channel, **defaults})
        # Never replace an editor's script or imported article during discovery.
        if created and channel.notify_admins:
            queue_admin_alert("youtube_blog_video", video, defer=True)
    return video, created


def prepare_captions(video):
    if video.transcript.strip():
        return False
    try:
        transcript = provider.fetch_transcript(video.video_id, language=video.channel.language)
    except provider.ProviderError as exc:
        YouTubeBlogVideo.objects.filter(pk=video.pk).update(transcript_error=str(exc)[:500], caption_checked_at=timezone.now())
        raise
    # A script pasted by a human during the provider request always wins.
    return bool(YouTubeBlogVideo.objects.filter(pk=video.pk, transcript=video.transcript).update(
        transcript=transcript, transcript_source="YouTube captions", transcript_error="", caption_checked_at=timezone.now(), updated_at=timezone.now()))


def sync_channel(channel_id, *, force=False, now=None):
    now = now or timezone.now()
    eligible = YouTubeBlogChannel.objects.filter(pk=channel_id).filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
    if not force:
        eligible = eligible.filter(automatic_checks=True).filter(Q(next_check_at__isnull=True) | Q(next_check_at__lte=now))
    lease = now + timedelta(minutes=15)
    if not eligible.update(lease_until=lease):
        return {"skipped": True, "created": 0, "caption_errors": 0}
    channel = YouTubeBlogChannel.objects.get(pk=channel_id)
    result = {"skipped": False, "created": 0, "caption_errors": 0, "outcome": "no_video"}
    error = ""
    try:
        resolved = provider.resolve_channel(channel.channel_url)
        if channel.channel_id and channel.channel_id != resolved["channel_id"]:
            raise provider.ProviderError("This URL now resolves to another channel. Add it as a separate channel to preserve the existing workspace.")
        channel.channel_id, channel.uploads_playlist_id = resolved["channel_id"], resolved["uploads_playlist_id"]
        YouTubeBlogChannel.objects.filter(pk=channel.pk).update(channel_id=channel.channel_id, uploads_playlist_id=channel.uploads_playlist_id)
        data = provider.latest_regular_video(channel.channel_id)
        if data is not None:
            video, created = save_video(channel, data)
            result["created"] = int(created)
            result["outcome"] = "added" if created else "removed" if video is None else "existing"
            # Retry missing captions only for this exact latest video. A title
            # duplicate may refer to another ID; never attach the wrong script.
            if (video is not None and channel.fetch_captions and video.video_id == data["video_id"]
                    and video.channel_id == channel.pk and not video.transcript.strip() and not video.blog_post_id):
                try:
                    prepare_captions(video)
                except provider.ProviderError:
                    result["caption_errors"] += 1
    except provider.ProviderError as exc:
        error = str(exc)[:500]
        raise
    except Exception:
        error = "The check could not complete. Try again or check the server logs."
        raise
    finally:
        # Compare the claim so an expired worker cannot clear a newer lease.
        YouTubeBlogChannel.objects.filter(pk=channel.pk, lease_until=lease).update(
            lease_until=None, last_checked_at=now, next_check_at=now + timedelta(minutes=channel.check_interval_minutes), last_error=error)
    return result


def add_video(channel, video_url):
    resolved = provider.resolve_channel(channel.channel_url)
    data = provider.fetch_video(video_url)
    if resolved["channel_id"] != data["channel_id"]:
        raise provider.ProviderError("This video does not belong to the selected YouTube channel.")
    return save_video(channel, data, manual=True)


@transaction.atomic
def delete_workspace_videos(queryset):
    # Use the same channel locks as discovery so a concurrent check cannot
    # recreate an item between its deletion and recording the suppression.
    channel_ids = queryset.order_by().values_list("channel_id", flat=True).distinct()
    list(YouTubeBlogChannel.objects.filter(pk__in=channel_ids).order_by("pk").select_for_update())
    for video in queryset:
        YouTubeBlogSuppression.objects.update_or_create(video_id=video.video_id,
            defaults={"channel_id": video.channel_id, "title": video.title})
    return queryset.delete()
