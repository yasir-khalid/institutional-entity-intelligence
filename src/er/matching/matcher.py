"""Orchestrator: retrieve candidates, score them, decide. The only file in this
package that talks to OpenSearch - features.py/scoring.py/decisions.py stay pure
and testable without a live cluster.
"""

from __future__ import annotations

from opensearchpy import OpenSearch

from er.config import AppConfig, MatchingDecisionThresholds
from er.matching.decisions import decide
from er.matching.features import build_query_record, compute_features
from er.matching.models import CandidateScore, Decision, MatchResult
from er.matching.scoring import explain, score_candidate
from er.retrieval.candidates import search_candidates

# Which query fields feed which evidence - used to tell the caller what extra
# information would actually move the needle, rather than just "not confident."
_EVIDENCE_FIELD_LABELS = {
    "country": "country/jurisdiction",
    "postcode": "postcode/address",
    "registration_id": "registration identifier",
}


def _missing_evidence(query: dict) -> list[str]:
    return [label for field, label in _EVIDENCE_FIELD_LABELS.items() if not query.get(field)]


def _build_reason(
    decision: Decision,
    scored: list[CandidateScore],
    thresholds: MatchingDecisionThresholds,
) -> tuple[str | None, list[CandidateScore]]:
    """Returns (human-readable reason, competing candidates) for REVIEW/UNMATCHED.
    None/[] for AUTO_MATCH - there's nothing to explain when it worked."""
    if decision == Decision.AUTO_MATCH or not scored:
        return None, []

    top_score = scored[0].score
    competing = [c for c in scored if top_score - c.score <= thresholds.tie_tolerance]

    if len(competing) > 1:
        jurisdictions = ", ".join(c.jurisdiction or "?" for c in competing)
        reason = (
            f"{len(competing)} entities share very similar evidence for this query "
            f"(within {thresholds.tie_tolerance:.0f} points of each other: {jurisdictions}) - "
            "the query doesn't contain enough information to distinguish them."
        )
        return reason, competing

    if decision == Decision.REVIEW:
        reason = (
            f"Top candidate score ({top_score:.0f}) clears the review threshold but not "
            "the auto-match threshold - there's a plausible candidate, but the evidence "
            "isn't strong enough to act on automatically."
        )
    else:
        reason = f"Top candidate score ({top_score:.0f}) is too low to be a plausible match."
    return reason, []


def match(
    client: OpenSearch,
    cfg: AppConfig,
    name: str,
    country: str | None = None,
    postcode: str | None = None,
    city: str | None = None,
    registration_id: str | None = None,
    country_mode: str = "soft",
) -> MatchResult:
    query = build_query_record(name, country, postcode, city, registration_id)

    raw_candidates = search_candidates(
        client, cfg, name, country, size=cfg.matching.candidate_pool_size, country_mode=country_mode
    )

    scored = []
    for c in raw_candidates:
        features = compute_features(query, c)
        score = score_candidate(features, cfg.matching.weights, cfg.matching.penalties)
        evidence = explain(features, cfg.matching.weights, cfg.matching.penalties)
        scored.append(
            CandidateScore(
                lei=c["lei"],
                legal_name=c["legal_name"],
                jurisdiction=c.get("jurisdiction"),
                score=score,
                retrieval_score=c.get("score"),
                rank=0,
                evidence=evidence,
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(scored):
        c.rank = i + 1

    decision, chosen, gap = decide(scored, cfg.matching.decision)
    reason, competing = _build_reason(decision, scored, cfg.matching.decision)

    return MatchResult(
        query_name=name,
        decision=decision,
        lei=chosen.lei if chosen else None,
        score=chosen.score if chosen else None,
        gap=gap,
        evidence=chosen.evidence if chosen else {},
        candidates=scored,
        reason=reason,
        missing_evidence=_missing_evidence(query) if decision != Decision.AUTO_MATCH else [],
        competing_candidates=competing,
    )
