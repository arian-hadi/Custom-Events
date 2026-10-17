import json

from django.core.management.base import BaseCommand, CommandError

from shop.amazon import purge_expired, sync_sources
from shop.amazon_provider import AmazonError


class Command(BaseCommand):
    help = "Refresh curated Amazon ASINs with Creators API; disabled until configured."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--source", action="append", type=int, dest="source_ids")
        parser.add_argument("--force", action="store_true", help="Refresh even when not due; does not bypass source enablement or active claims.")
        parser.add_argument("--dry-run", action="store_true", help="List due source IDs without any network requests or writes.")
        parser.add_argument("--purge-only", action="store_true", help="Remove expired provider content, even when automation is disabled.")

    def handle(self, *args, **options):
        if options["purge_only"] and options["dry_run"]:
            raise CommandError("Use --purge-only or --dry-run separately.")
        try:
            result = purge_expired() if options["purge_only"] else sync_sources(
                limit=options["limit"], force=options["force"], dry_run=options["dry_run"], source_ids=options["source_ids"],
            )
        except AmazonError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(result))
        if result.get("failed"):
            raise CommandError("Some Amazon sources failed; inspect Amazon sync runs and source retry information in admin.")
