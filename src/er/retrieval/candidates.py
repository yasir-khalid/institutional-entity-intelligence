"""Candidate retrieval: OpenSearch is used to find plausible GLEIF entities, not to
decide the match. `_score` here is a retrieval-relevance score, not a match probability
- see the (later) matching/scoring milestone for the actual decision layer.
"""

from __future__ import annotations

from opensearchpy import OpenSearch

from er.config import AppConfig
from er.normalisation.names import build_name_fields


def build_candidate_query(name: str, country: str | None, size: int) -> dict:
    fields = build_name_fields(name)

    should = [
        {"match": {"legal_name_norm": {"query": fields["legal_name_norm"], "boost": 5}}},
        {"match": {"legal_name_core": {"query": fields["legal_name_core"], "boost": 3}}},
        {"match": {"aliases_norm": {"query": fields["legal_name_norm"], "boost": 2}}},
    ]

    query: dict = {"bool": {"should": should, "minimum_should_match": 1}}

    if country:
        query["bool"]["filter"] = [{"term": {"legal_country": country.upper()}}]

    return {"size": size, "query": query}


def search_candidates(
    client: OpenSearch,
    cfg: AppConfig,
    name: str,
    country: str | None = None,
    size: int | None = None,
) -> list[dict]:
    body = build_candidate_query(name, country, size or cfg.search.default_size)
    resp = client.search(index=cfg.opensearch.index_name, body=body)
    return [
        {
            "rank": i + 1,
            "score": hit["_score"],
            "lei": hit["_source"]["lei"],
            "legal_name": hit["_source"]["legal_name"],
            "jurisdiction": hit["_source"].get("jurisdiction"),
            "legal_country": hit["_source"].get("legal_country"),
        }
        for i, hit in enumerate(resp["hits"]["hits"])
    ]
