from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from platform_api.models import YouTubeBlogChannel
from platform_api.youtube_blog import sync_channel
from platform_api.youtube_source import ProviderError


class Command(BaseCommand):
    help = "Check each channel's newest regular video only; skip stored IDs/titles and never publish articles."

    def add_arguments(self, parser):
        parser.add_argument("--channel", type=int, help="Manually check this channel, even when automatic checks are off.")

    def handle(self, *args, **options):
        channels = YouTubeBlogChannel.objects.order_by("pk")
        if options["channel"]:
            channels = channels.filter(pk=options["channel"])
            if not channels.exists():
                raise CommandError("YouTube channel not found in the blog workspace.")
        else:
            channels = channels.filter(automatic_checks=True).filter(Q(next_check_at__isnull=True) | Q(next_check_at__lte=timezone.now()))[:10]
        failed = False
        for channel in channels:
            try:
                result = sync_channel(channel.pk, force=bool(options["channel"]))
                self.stdout.write(f"Channel #{channel.pk}: {result['created']} new video(s); {result['caption_errors']} caption issue(s).")
            except ProviderError as exc:
                self.stderr.write(f"Channel #{channel.pk}: {exc}")
                failed = True
        if failed:
            raise CommandError("Some YouTube checks failed. See channel status in administration.")
