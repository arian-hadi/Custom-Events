import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from edithub.league.calibration import build_references
from edithub.league.scoring import default_config
from edithub.league_models import MetricSnapshot, ScoringVersion


class Command(BaseCommand):
    help = "Build a draft scoring version from explicitly selected real pilot snapshot IDs. Never enables scoring."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--snapshots", required=True, help="JSON file containing a list of MetricSnapshot IDs.")
        parser.add_argument("--formats", required=True, help="Comma-separated provider formats, e.g. youtube:unknown.")
        parser.add_argument("--prior-views", required=True)
        parser.add_argument("--baseline-floor", required=True)
        parser.add_argument("--improvement-cap", required=True)
        parser.add_argument("--minimum-samples", type=int, default=20)
        parser.add_argument("--save", action="store_true", help="Save as an unconfirmed, uncalibrated draft; otherwise output JSON only.")

    def handle(self, *args, **options):
        try:
            identifiers = json.loads(Path(options["snapshots"]).read_text(encoding="utf-8-sig"))
            if not isinstance(identifiers, list) or not identifiers or any(type(pk) is not int or pk < 1 for pk in identifiers):
                raise ValueError("The pilot file must contain positive integer snapshot IDs.")
            rows = list(MetricSnapshot.objects.filter(pk__in=identifiers))
            if len(rows) != len(set(identifiers)):
                raise ValueError("Some pilot observations do not exist.")
            config = default_config()
            config["supported_formats"] = list(dict.fromkeys(value.strip() for value in options["formats"].split(",") if value.strip()))
            config, evidence = build_references(config, rows, prior_views=options["prior_views"],
                baseline_floor=options["baseline_floor"], improvement_cap=options["improvement_cap"],
                minimum_samples=options["minimum_samples"])
            document = {"config": config, "evidence": evidence}
            if options["save"]:
                with transaction.atomic():
                    if ScoringVersion.objects.filter(name=options["name"]).exists():
                        raise ValueError("Choose a new version name; existing versions are never overwritten.")
                    version = ScoringVersion.objects.create(name=options["name"], config=config,
                        calibration_notes=json.dumps(evidence, indent=2))
                self.stdout.write(f"Created draft {version.name}. Review evidence, rules and parameters in admin before approval.")
            else:
                self.stdout.write(json.dumps(document, indent=2))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
