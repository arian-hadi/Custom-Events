from typing import Optional

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from edithub.models import EditorApplication
from edithub.utils import (
    fetch_youtube_channel_data,
    fetch_tiktok_channel_data,
)


class Command(BaseCommand):
    help = (
        "Fetch latest channel data (followers, name, thumbnail) for accepted applications "
        "and refresh rankings. Intended to run weekly."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--only",
            choices=["youtube", "tiktok"],
            help="Limit updates to a single platform.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Process only the first N applications (useful for testing).",
        )

    def handle(self, *args, **options):
        platform_filter: Optional[str] = options.get("only")
        limit: Optional[int] = options.get("limit")

        queryset = EditorApplication.objects.filter(
            status="accepted",
            removal_requested=False,
        ).order_by("-updated_date")

        if platform_filter:
            queryset = queryset.filter(channel_type=platform_filter)

        if limit:
            queryset = queryset[:limit]

        total = queryset.count()
        updated = 0
        failed = 0
        started_at = timezone.now()

        self.stdout.write(
            self.style.NOTICE(
                f"Starting weekly update for {total} application(s)"
                + (f" [only={platform_filter}]" if platform_filter else "")
                + (f" [limit={limit}]" if limit else "")
            )
        )

        for app in queryset:
            try:
                if app.channel_type == "youtube":
                    data = fetch_youtube_channel_data(app.channel_link)
                else:
                    data = fetch_tiktok_channel_data(app.channel_link)

                if data.get("error"):
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skip {app.pk} ({app.channel_type}) - fetch error: {data['error']}"
                        )
                    )
                    continue

                # Collect potential updates
                new_name = data.get("channel_name") or app.channel_name
                new_followers = (
                    data.get("subscriber_count") or data.get("follower_count") or app.follower_count
                )
                # Get thumbnail from API (strip whitespace)
                api_thumb = (data.get("thumbnail") or "").strip()

                fields_to_update = []
                if new_name and new_name != app.channel_name:
                    app.channel_name = new_name
                    fields_to_update.append("channel_name")
                # Update thumbnail if we got a valid one from API and it's different
                # This will also update empty thumbnails
                if api_thumb and api_thumb != (app.channel_thumbnail or "").strip():
                    app.channel_thumbnail = api_thumb
                    fields_to_update.append("channel_thumbnail")
                if new_followers is not None and new_followers != app.follower_count:
                    app.follower_count = new_followers
                    fields_to_update.append("follower_count")

                if fields_to_update:
                    # updated_date will change automatically on save
                    app.save(update_fields=fields_to_update + ["updated_date"])
                    updated += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to update app {app.pk} ({app.channel_type}): {exc}"
                    )
                )

        # Recalculate and snapshot ranks (weekly snapshot logic lives in model method)
        with transaction.atomic():
            EditorApplication.update_rank_positions()

        elapsed = (timezone.now() - started_at).total_seconds()
        self.stdout.write(
            self.style.SUCCESS(
                f"Weekly update completed: total={total}, updated={updated}, failed={failed}, elapsed={elapsed:.1f}s"
            )
        )


