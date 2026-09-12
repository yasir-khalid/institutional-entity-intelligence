"""Candidate retrieval: OpenSearch is used to find plausible GLEIF entities, not to
decide the match. `_score` here is a retrieval-relevance score, not a match probability
- see the (later) matching/scoring milestone for the actual decision layer.
"""

from __future__ import annotations

from opensearchpy import OpenSearch

from er.config import AppConfig
from er.normalisation.countries import normalize_country_code
from er.normalisation.names import build_name_fields

# How much a country match/mismatch influences retrieval, relative to the name
# clauses' boosts (5/3/2 below). "Soft" mode intentionally uses a large boost so a
# correct country still sharpens ranking meaningfully, without ever excluding a
# candidate the way a hard filter would.
SOFT_COUNTRY_MATCH_BOOST = 8
SOFT_COUNTRY_MISMATCH_PENALTY = 0.3  # negative_boost multiplier, applied via `boosting`

COUNTRY_MODES = ("soft", "strict")


def build_candidate_query(
    name: str, country: str | None, size: int, country_mode: str = "soft"
) -> dict:
    if country_mode not in COUNTRY_MODES:
        raise ValueError(f"country_mode must be one of {COUNTRY_MODES}, got {country_mode!r}")

    fields = build_name_fields(name)
    country_code = normalize_country_code(country)  # "UK"/"United Kingdom" -> "GB", etc.

    should = [
        {"match": {"legal_name_norm": {"query": fields["legal_name_norm"], "boost": 5}}},
        {"match": {"legal_name_core": {"query": fields["legal_name_core"], "boost": 3}}},
        {"match": {"aliases_norm": {"query": fields["legal_name_norm"], "boost": 2}}},
    ]
    name_query: dict = {"bool": {"should": should, "minimum_should_match": 1}}

    if not country_code:
        return {"size": size, "query": name_query}

    if country_mode == "strict":
        # An explicit, deliberate hard filter: the caller is certain of the country
        # and wants non-matching candidates excluded entirely. Contrast with "soft"
        # (the default) - a hard filter silently drops the true entity whenever the
        # source's country field is merely wrong or uncertain, which is the common
        # case for real messy data (confirmed live: the true GB entity for "NORTH
        # ROCK CAPITAL MANAGEMENT (UK) LLP" vanished entirely under a hard filter
        # with an incorrect country). Use strict only when the caller trusts the
        # country field completely.
        query = {"bool": {**name_query["bool"], "filter": [{"term": {"legal_country": country_code}}]}}
        return {"size": size, "query": query}

    # soft: large boost for a match, a real (if smaller) penalty for a mismatch -
    # via `boosting`, not a plain `should` addition, so a wrong country actively
    # pushes a candidate down rather than merely failing to push it up.
    should.append({"term": {"legal_country": {"value": country_code, "boost": SOFT_COUNTRY_MATCH_BOOST}}})
    query = {
        "boosting": {
            "positive": {"bool": {"should": should, "minimum_should_match": 1}},
            "negative": {"bool": {"must_not": [{"term": {"legal_country": country_code}}]}},
            "negative_boost": SOFT_COUNTRY_MISMATCH_PENALTY,
        }
    }
    return {"size": size, "query": query}


def search_candidates(
    client: OpenSearch,
    cfg: AppConfig,
    name: str,
    country: str | None = None,
    size: int | None = None,
    country_mode: str = "soft",
) -> list[dict]:
    """Returns each hit's full indexed document (see RETRIEVAL_FIELDS in
    er.indexing.opensearch_index) plus rank/score - not just a display-friendly
    subset - so downstream consumers (e.g. er.matching) have every field to compare
    against without a second lookup.
    """
    body = build_candidate_query(name, country, size or cfg.search.default_size, country_mode)
    resp = client.search(index=cfg.opensearch.index_name, body=body)
    return [
        {"rank": i + 1, "score": hit["_score"], **hit["_source"]}
        for i, hit in enumerate(resp["hits"]["hits"])
    ]
