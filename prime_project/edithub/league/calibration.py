"""Build reviewable pilot references from immutable provider observations.

This never approves calibration or enables the league. Smoothing parameters are
explicit administrator choices; observations and methodology remain in evidence.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
from statistics import median

from .scoring import CalibrationRequired, age_band, decimal, validate_config


def empirical_knots(values):
    """Empirical mid-ranks, rescaled to the supported clamped 0–100 mapping."""
    ordered = sorted(decimal(value) for value in values)
    groups = defaultdict(list)
    for index, value in enumerate(ordered):
        groups[value].append(Decimal(index))
    ranks = [(value, sum(indices) / len(indices)) for value, indices in sorted(groups.items())]
    if len(ranks) < 2:
        raise CalibrationRequired("Pilot samples need at least two distinct values for each component.")
    low, high = ranks[0][1], ranks[-1][1]
    return [[str(value), str((rank - low) * 100 / (high - low))] for value, rank in ranks]


def build_references(config, observations, *, prior_views, baseline_floor, improvement_cap, minimum_samples=20):
    config = deepcopy(config)
    parameters = {"prior_views": decimal(prior_views), "baseline_floor": decimal(baseline_floor),
                  "improvement_cap": decimal(improvement_cap)}
    if any(value <= 0 for value in parameters.values()) or minimum_samples < 5:
        raise CalibrationRequired("Positive smoothing parameters and at least five pilot samples per bucket are required.")
    buckets = defaultdict(dict)
    history_buckets = defaultdict(list)
    for row in observations:
        if (row.status != "success" or row.likes is None or row.views is None or not row.provider
                or row.likes < 0 or row.views < 0 or row.likes > row.views
                or row.completed_at < row.published_at):
            raise CalibrationRequired(f"Observation {row.pk} is not usable provider evidence.")
        band = age_band(config, (row.completed_at - row.published_at).total_seconds())
        key = f"{row.platform}:{row.video_format}:{band}"
        history_buckets[key].append(row)
        identity = (row.platform, row.video_id)
        previous = buckets[key].get(identity)
        if previous is None or (row.completed_at, row.pk) > (previous.completed_at, previous.pk):
            buckets[key][identity] = row
    evidence, references = {}, {}
    with localcontext() as context:
        context.prec = 48
        for supported in config["supported_formats"]:
            for band in config["age_bands"]:
                key = f"{supported}:{band['key']}"
                rows = list(buckets[key].values())
                if len(rows) < minimum_samples:
                    raise CalibrationRequired(f"{key}: {len(rows)} distinct videos; {minimum_samples} required.")
                total_views = sum(row.views for row in rows)
                if not total_views:
                    raise CalibrationRequired(f"{key}: no observed views.")
                prior_rate = Decimal(sum(row.likes for row in rows)) / total_views
                response = [(Decimal(row.likes) + prior_rate * parameters["prior_views"]) /
                            (Decimal(row.views) + parameters["prior_views"]) for row in rows]
                improvement, baseline_evidence = [], {}
                for row in rows:
                    # Comparable age, same creator/format; only observations
                    # already available when this pilot observation was made.
                    target_age = row.completed_at - row.published_at
                    nearest = {}
                    for other in history_buckets[key]:
                        if (other.editor_id != row.editor_id or other.video_id == row.video_id
                                or other.published_at >= row.published_at or other.completed_at > row.completed_at
                                or other.received_at > row.received_at):
                            continue
                        distance = (abs((other.completed_at - other.published_at) - target_age), other.completed_at, other.pk)
                        if other.video_id not in nearest or distance < nearest[other.video_id][0]:
                            nearest[other.video_id] = (distance, other)
                    history = sorted((pair[1] for pair in nearest.values()),
                        key=lambda other: (other.published_at, other.pk), reverse=True)[:config["baseline_max_samples"]]
                    if len(history) >= config["baseline_min_samples"]:
                        baseline = median([Decimal(other.likes) for other in history])
                        improvement.append(min(Decimal(row.likes) / max(baseline, parameters["baseline_floor"]),
                                               parameters["improvement_cap"]))
                        baseline_evidence[str(row.pk)] = [other.pk for other in history]
                if len(improvement) < minimum_samples:
                    raise CalibrationRequired(f"{key}: {len(improvement)} comparable creator ratios; {minimum_samples} required.")
                references[key] = {**{name: str(value) for name, value in parameters.items()},
                    "prior_rate": str(prior_rate), "response": empirical_knots(response),
                    "improvement": empirical_knots(improvement),
                    "popularity": empirical_knots([row.likes for row in rows])}
                evidence[key] = {"snapshot_ids": sorted(row.pk for row in rows),
                    "editors": len({row.editor_id for row in rows}), "videos": len(rows),
                    "improvement_samples": len(improvement), "baseline_snapshot_ids": baseline_evidence}
    config["references"] = references
    validate_config(config)
    return config, {"method": "provider_snapshot_empirical_midrank_v1", "minimum_samples": minimum_samples,
                    "buckets": evidence, "review_required": True}
