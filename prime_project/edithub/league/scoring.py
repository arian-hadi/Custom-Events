"""Pure, versioned decimal scoring. Default references are intentionally absent."""
from decimal import Decimal, DecimalException, InvalidOperation, localcontext


class LeagueError(ValueError):
    pass


class CalibrationRequired(LeagueError):
    pass


class DataPending(LeagueError):
    pass


def default_config():
    return {
        "timezone": "UTC", "intake": "next_week", "repeat_policy": "one_per_month",
        "weights": {"response": "0.50", "improvement": "0.30", "popularity": "0.20"},
        "minimum_entries": 5, "baseline_min_samples": 5, "baseline_max_samples": 8,
        "neutral_improvement": "50", "cutoff_max_age_seconds": 900,
        "placement_points": [25, 20, 16, 13, 11, 10, 9, 8, 7, 6], "finisher_points": 2,
        "age_bands": [
            {"key": "under_7", "min_days": 0, "max_days": 7},
            {"key": "7_29", "min_days": 7, "max_days": 30},
            {"key": "30_89", "min_days": 30, "max_days": 90},
            {"key": "90_plus", "min_days": 90, "max_days": None},
        ],
        "supported_formats": ["youtube:short", "tiktok:short"],
        "references": {}, "mapping_policy": "linear_knots_clamped_v1",
        "tie_policy": "score_response_improvement_seeded_draw_v1",
        "precision": 48,
    }


def automatic_config():
    """Transparent starter rules; no fabricated pilot distributions or approval."""
    config = default_config()
    config.update(mapping_policy="round_cohort_v2", supported_formats=[
        "youtube:unknown", "youtube:short", "youtube:long", "youtube:video", "tiktok:video", "tiktok:short",
    ], baseline_floor="1", improvement_cap="5", popularity_metric="views",
        baseline_policy="website_last_five_v1", baseline_min_samples=1, baseline_max_samples=5,
        debut_improvement_score="85")
    return config


def is_cohort(config):
    return config.get('mapping_policy') in {'round_cohort_v1', 'round_cohort_v2'}


def version_ready(version):
    if not version or not version.rules_confirmed:
        return False
    try:
        validate_config(version.config)
    except ValueError:
        return False
    return is_cohort(version.config) or bool(version.calibrated and version.calibration_notes.strip())


def score_cohort(config, observations, *, debut_ids=()):
    """Mid-rank percentiles of genuine round observations, with disclosed neutral history.

    Input is {entry_id: (lifetime likes, lifetime views, frozen creator median)}.
    Equal component values share a percentile. One comparable value scores 50.
    This launch policy is not an empirically calibrated fairness claim.
    """
    validate_config(config)
    revised = config.get('mapping_policy') == 'round_cohort_v2'
    debut_ids = set(debut_ids) if revised else set()
    with localcontext() as context:
        context.prec = config['precision']
        raw = {}
        for identity, (likes, views, median) in observations.items():
            if likes is None or views is None or decimal(likes) < 0 or decimal(views) < 0:
                raise DataPending("Valid nonnegative lifetime likes and views are required.")
            likes, views = decimal(likes), decimal(views)
            if views == 0 and likes > 0:
                raise DataPending("Likes without views require a consistent provider observation.")
            raw[identity] = (likes / views if views else Decimal(0),
                None if median is None or identity in debut_ids else min(likes / max(decimal(median), decimal(config['baseline_floor'])), decimal(config['improvement_cap'])),
                views if revised else likes)

        def rank(value, index):
            values = [item[index] for item in raw.values() if item[index] is not None]
            if len(values) <= 1:
                return Decimal(50)
            below = sum(item < value for item in values)
            tied = sum(item == value for item in values)
            return (Decimal(below) + Decimal(tied - 1) / 2) * 100 / (len(values) - 1)

        results = {}
        for identity, (rate, relative, popularity_value) in raw.items():
            response = rank(rate, 0)
            improvement = decimal(config['neutral_improvement']) if relative is None else rank(relative, 1)
            debut = identity in debut_ids
            if debut:
                improvement = decimal(config['debut_improvement_score'])
            popularity = rank(popularity_value, 2)
            total = sum(value * decimal(config['weights'][key]) for key, value in (
                ('response', response), ('improvement', improvement), ('popularity', popularity)))
            results[identity] = dict(response_score=str(response), improvement_score=str(improvement),
                popularity_score=str(popularity), weekly_score=str(total), adjusted_like_rate=str(rate),
                relative_performance=None if relative is None else str(relative), neutral_improvement=relative is None and not debut,
                likes=str(observations[identity][0]), views=str(observations[identity][1]),
                scoring_method=config['mapping_policy'], cohort_size=len(raw),
                debut_bonus=debut, popularity_metric='views' if revised else 'likes',
                improvement_weight=config['weights']['improvement'])
        return results


def decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LeagueError("A finite decimal value is required.") from exc
    if not number.is_finite():
        raise LeagueError("A finite decimal value is required.")
    return number


def validate_config(config):
    """Validate complete coverage, never substitute invented pilot distributions."""
    try:
        return _validate_config(config)
    except CalibrationRequired:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, DecimalException) as exc:
        # Draft versions are admin-authored JSON. An unexpected container or
        # malformed decimal must be a form/command error, never a server error.
        raise CalibrationRequired("Scoring configuration contains a missing or malformed value.") from exc


def _validate_config(config):
    if not isinstance(config, dict):
        raise CalibrationRequired("Scoring configuration must be a JSON object.")
    if config.get("timezone") != "UTC" or config.get("intake") != "next_week":
        raise CalibrationRequired("Only the UTC following-week calendar is implemented.")
    # Legacy frozen versions retain their recorded metadata. New intake uses
    # monthly database uniqueness; this does not rewrite historical scores.
    if config.get("repeat_policy") not in {"one_v2_result", "one_per_month"}:
        raise CalibrationRequired("Unsupported repeat-entry policy.")
    if config.get("mapping_policy") not in {"linear_knots_clamped_v1", "round_cohort_v1", "round_cohort_v2"} or config.get("tie_policy") != "score_response_improvement_seeded_draw_v1":
        raise CalibrationRequired("Unsupported scoring or tie policy.")
    weights = config.get("weights", {})
    if not isinstance(weights, dict) or set(weights) != {"response", "improvement", "popularity"} or sum(decimal(v) for v in weights.values()) != 1 or any(decimal(v) < 0 for v in weights.values()):
        raise CalibrationRequired("Component weights must be nonnegative and sum to one.")
    for key in ("minimum_entries", "baseline_min_samples", "baseline_max_samples", "cutoff_max_age_seconds", "precision"):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise CalibrationRequired(f"Invalid {key}.")
    if config["precision"] != 48 or config["baseline_min_samples"] > config["baseline_max_samples"]:
        raise CalibrationRequired("Invalid precision or sample limits.")
    if not 0 <= decimal(config["neutral_improvement"]) <= 100:
        raise CalibrationRequired("Neutral improvement must be between zero and 100.")
    points = config.get("placement_points", [])
    if not isinstance(points, list) or not points or any(type(value) is not int or value < 0 for value in points + [config.get("finisher_points")]):
        raise CalibrationRequired("League points must be nonnegative integers.")
    bands = config.get("age_bands", [])
    if not isinstance(bands, list):
        raise CalibrationRequired("Age bands must be a list of objects.")
    cursor, names = 0, set()
    for index, band in enumerate(bands):
        if not isinstance(band, dict) or type(band.get("min_days")) is not int or band.get("min_days") != cursor or not isinstance(band.get("key"), str) or not band["key"].strip() or band["key"] in names:
            raise CalibrationRequired("Age bands must be unique, contiguous and start at zero.")
        names.add(band["key"])
        maximum = band.get("max_days")
        if maximum is None:
            if index != len(bands) - 1:
                raise CalibrationRequired("Only the final age band may be unbounded.")
        elif type(maximum) is not int or maximum <= cursor:
            raise CalibrationRequired("Invalid age-band boundary.")
        cursor = maximum
    if not bands or cursor is not None:
        raise CalibrationRequired("Reference coverage must include older edits.")
    formats = config.get("supported_formats", [])
    if not isinstance(formats, list) or not formats or any(not isinstance(value, str) or not value.strip() for value in formats) or len(formats) != len(set(formats)):
        raise CalibrationRequired("At least one calibrated platform and format is required.")
    if is_cohort(config):
        if decimal(config.get('baseline_floor')) <= 0 or decimal(config.get('improvement_cap')) <= 0:
            raise CalibrationRequired('Automatic baseline floor and improvement cap must be positive.')
        if config['mapping_policy'] == 'round_cohort_v2':
            if config.get('popularity_metric') != 'views' or config.get('baseline_policy') != 'website_last_five_v1':
                raise CalibrationRequired('V2 requires views and website submission history.')
            if config['baseline_min_samples'] != 1 or config['baseline_max_samples'] != 5:
                raise CalibrationRequired('V2 uses one to five previous finalized edits.')
            if not 0 <= decimal(config.get('debut_improvement_score')) <= 100:
                raise CalibrationRequired('Debut performance must be between zero and 100.')
        return config
    references = config.get("references", {})
    if not isinstance(references, dict):
        raise CalibrationRequired("References must map platform, format and age keys to objects.")
    for supported in formats:
        for band in bands:
            key = f"{supported}:{band['key']}"
            reference = references.get(key)
            if not isinstance(reference, dict) or not reference:
                raise CalibrationRequired(f"Missing pilot calibration: {key}.")
            if not 0 <= decimal(reference.get("prior_rate")) <= 1:
                raise CalibrationRequired("Invalid response prior.")
            for parameter in ("prior_views", "baseline_floor", "improvement_cap"):
                if decimal(reference.get(parameter)) <= 0:
                    raise CalibrationRequired(f"{parameter} must be positive.")
            for component in ("response", "improvement", "popularity"):
                knots = reference.get(component, [])
                if not isinstance(knots, list) or len(knots) < 2 or any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in knots):
                    raise CalibrationRequired(f"Insufficient {component} reference points.")
                prior_x, prior_y = None, None
                for x, y in knots:
                    x, y = decimal(x), decimal(y)
                    if x < 0 or not 0 <= y <= 100 or (prior_x is not None and (x <= prior_x or y < prior_y)):
                        raise CalibrationRequired("Reference knots require increasing inputs and nondecreasing percentiles.")
                    prior_x, prior_y = x, y
                if decimal(knots[0][1]) != 0 or decimal(knots[-1][1]) != 100:
                    raise CalibrationRequired("Reference distributions must cover percentiles zero through 100.")
    return config


def age_band(config, age_seconds):
    days = decimal(age_seconds) / Decimal(86400)
    if days < 0:
        raise LeagueError("Publication cannot follow the scoring cutoff.")
    for band in config["age_bands"]:
        if days >= band["min_days"] and (band["max_days"] is None or days < band["max_days"]):
            return band["key"]
    raise CalibrationRequired("No reference age band covers this entry.")


def percentile(value, knots):
    value = decimal(value)
    pairs = [(decimal(x), decimal(y)) for x, y in knots]
    if value <= pairs[0][0]:
        return pairs[0][1]
    for (left, low), (right, high) in zip(pairs, pairs[1:]):
        if value <= right:
            return low + (value - left) * (high - low) / (right - left)
    return pairs[-1][1]


def score(config, reference_key, likes, views, baseline_median=None):
    reference = config.get("references", {}).get(reference_key)
    if reference is None:
        raise CalibrationRequired(f"Missing pilot calibration: {reference_key}.")
    if likes is None or views is None or likes < 0 or views < 0:
        raise DataPending("Valid nonnegative lifetime likes and views are required.")
    with localcontext() as context:
        context.prec = config.get("precision", 48)
        likes, views = decimal(likes), decimal(views)
        rate = (likes + decimal(reference["prior_rate"]) * decimal(reference["prior_views"])) / (views + decimal(reference["prior_views"]))
        response = percentile(rate, reference["response"])
        neutral = baseline_median is None
        relative = None if neutral else min(likes / max(decimal(baseline_median), decimal(reference["baseline_floor"])), decimal(reference["improvement_cap"]))
        improvement = decimal(config["neutral_improvement"]) if neutral else percentile(relative, reference["improvement"])
        popularity = percentile(likes, reference["popularity"])
        weights = config["weights"]
        total = response * decimal(weights["response"]) + improvement * decimal(weights["improvement"]) + popularity * decimal(weights["popularity"])
        return {"response_score": str(response), "improvement_score": str(improvement), "popularity_score": str(popularity),
                "weekly_score": str(total), "adjusted_like_rate": str(rate), "relative_performance": None if relative is None else str(relative),
                "neutral_improvement": neutral, "likes": str(likes), "views": str(views), "reference_key": reference_key}
