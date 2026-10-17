from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase

from edithub.league.calibration import build_references, empirical_knots
from edithub.league.scoring import CalibrationRequired, default_config


class PilotCalibrationTests(TestCase):
    def setUp(self):
        self.config = default_config()
        self.config["supported_formats"] = ["youtube:unknown"]
        self.config["age_bands"] = [{"key": "all", "min_days": 0, "max_days": None}]
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = [SimpleNamespace(pk=i + 1, platform="youtube", video_format="unknown",
            video_id=f"video-{i}", editor_id=1, status="success", provider="youtube-data-api",
            likes=(i + 1) ** 2, views=1000 + i * 20, published_at=start + timedelta(days=i),
            completed_at=start + timedelta(days=i + 2), received_at=start + timedelta(days=i + 2))
            for i in range(14)]

    def build(self, rows=None):
        return build_references(self.config, self.rows if rows is None else rows,
            prior_views="100", baseline_floor="5", improvement_cap="20", minimum_samples=5)

    def test_real_sample_knots_and_evidence_without_mutating_input(self):
        config, evidence = self.build()
        reference = config["references"]["youtube:unknown:all"]
        self.assertEqual(reference["popularity"][0], ["1", "0"])
        self.assertEqual(reference["popularity"][-1], ["196", "100"])
        self.assertEqual(self.config["references"], {})
        self.assertTrue(evidence["review_required"])
        self.assertEqual(evidence["buckets"]["youtube:unknown:all"]["videos"], 14)
        self.assertEqual(len(evidence["buckets"]["youtube:unknown:all"]["baseline_snapshot_ids"]), 9)

    def test_repeated_polling_does_not_inflate_distinct_video_samples(self):
        config, evidence = self.build(self.rows + self.rows)
        self.assertEqual(evidence["buckets"]["youtube:unknown:all"]["videos"], 14)

    def test_missing_age_bucket_never_fills_with_fake_reference(self):
        self.config["age_bands"] = default_config()["age_bands"]
        with self.assertRaisesRegex(CalibrationRequired, "7_29"):
            self.build()

    def test_insufficient_creator_history_is_not_a_neutral_pilot_distribution(self):
        for row in self.rows:
            row.editor_id = row.pk
        with self.assertRaisesRegex(CalibrationRequired, "comparable creator ratios"):
            self.build()

    def test_invalid_or_unavailable_metrics_are_rejected(self):
        self.rows[0].likes = None
        with self.assertRaisesRegex(CalibrationRequired, "not usable provider evidence"):
            self.build()

    def test_flat_distribution_is_not_invented(self):
        with self.assertRaises(CalibrationRequired):
            empirical_knots([4, 4, 4, 4, 4])

