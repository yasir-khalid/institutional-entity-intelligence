"""Turn a feature dict into a single deterministic score.

Deliberately not machine-learned: every point is traceable to one named weight or
penalty in config (`matching.weights` / `matching.penalties` in config/dev.yaml), so
retuning the matcher is a config edit, never a code change, and every score can be
explained by summing named contributions.
"""

from __future__ import annotations

from er.config import MatchingPenalties, MatchingWeights


def score_candidate(features: dict, weights: MatchingWeights, penalties: MatchingPenalties) -> float:
    score = 0.0

    if features["name_exact"]:
        score += weights.name_exact
    if features["name_core_exact"]:
        score += weights.name_core_exact
    score += features["name_ratio"] * weights.name_ratio

    if features["jurisdiction_exact"]:
        score += weights.jurisdiction_exact
    if features["country_exact"]:
        score += weights.country_exact
    if features["postcode_exact"]:
        score += weights.postcode_exact
    if features["postcode_prefix_exact"]:
        score += weights.postcode_prefix_exact
    if features["city_exact"]:
        score += weights.city_exact
    if features["fund_number_exact"]:
        score += weights.fund_number_exact
    if features["registration_id_exact"]:
        score += weights.registration_id_exact

    if features["fund_number_conflict"]:
        score -= penalties.fund_number_conflict
    if features["master_conflict"]:
        score -= penalties.master_conflict
    if features["feeder_conflict"]:
        score -= penalties.feeder_conflict
    if features["registration_id_conflict"]:
        score -= penalties.registration_id_conflict

    return score


def explain(features: dict, weights: MatchingWeights, penalties: MatchingPenalties) -> dict[str, float]:
    """Named score contributions - what actually made up the total, for the
    evidence a reviewer or the CLI shows. Zero-contribution features are omitted."""
    contributions: dict[str, float] = {}

    def add(name: str, condition, weight: float) -> None:
        if condition:
            contributions[name] = weight

    add("name_exact", features["name_exact"], weights.name_exact)
    add("name_core_exact", features["name_core_exact"], weights.name_core_exact)
    if features["name_ratio"]:
        contributions["name_ratio"] = round(features["name_ratio"] * weights.name_ratio, 2)
    add("jurisdiction_exact", features["jurisdiction_exact"], weights.jurisdiction_exact)
    add("country_exact", features["country_exact"], weights.country_exact)
    add("postcode_exact", features["postcode_exact"], weights.postcode_exact)
    add("postcode_prefix_exact", features["postcode_prefix_exact"], weights.postcode_prefix_exact)
    add("city_exact", features["city_exact"], weights.city_exact)
    add("fund_number_exact", features["fund_number_exact"], weights.fund_number_exact)
    add("registration_id_exact", features["registration_id_exact"], weights.registration_id_exact)
    add("fund_number_conflict", features["fund_number_conflict"], -penalties.fund_number_conflict)
    add("master_conflict", features["master_conflict"], -penalties.master_conflict)
    add("feeder_conflict", features["feeder_conflict"], -penalties.feeder_conflict)
    add("registration_id_conflict", features["registration_id_conflict"], -penalties.registration_id_conflict)

    return contributions
