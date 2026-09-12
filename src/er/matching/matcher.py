"""Orchestrator: retrieve candidates, score them, decide. The only file in this
package that talks to OpenSearch - features.py/scoring.py/decisions.py stay pure
and testable without a live cluster.
"""

from __future__ import annotations

from opensearchpy import OpenSearch

from er.config import AppConfig
from er.matching.decisions import decide
from er.matching.features import build_query_record, compute_features
from er.matching.models import CandidateScore, MatchResult
from er.matching.scoring import explain, score_candidate
from er.retrieval.candidates import search_candidates


def match(
    client: OpenSearch,
    cfg: AppConfig,
    name: str,
    country: str | None = None,
    postcode: str | None = None,
    city: str | None = None,
    registration_id: str | None = None,
) -> MatchResult:
    query = build_query_record(name, country, postcode, city, registration_id)

    raw_candidates = search_candidates(
        client, cfg, name, country, size=cfg.matching.candidate_pool_size
    )

    scored = []
    for c in raw_candidates:
        features = compute_features(query, c)
        score = score_candidate(features, cfg.matching.weights, cfg.matching.penalties)
        evidence = explain(features, cfg.matching.weights, cfg.matching.penalties)
        scored.append(
            CandidateScore(lei=c["lei"], legal_name=c["legal_name"], score=score, rank=0, evidence=evidence)
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(scored):
        c.rank = i + 1

    decision, chosen, gap = decide(scored, cfg.matching.decision)

    return MatchResult(
        query_name=name,
        decision=decision,
        lei=chosen.lei if chosen else None,
        score=chosen.score if chosen else None,
        gap=gap,
        evidence=chosen.evidence if chosen else {},
        candidates=scored,
    )
