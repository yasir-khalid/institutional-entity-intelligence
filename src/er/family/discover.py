"""Orchestrator: retrieve a broad candidate pool, classify each by brand-core tier,
confirm with intra-pool graph evidence. The only file in this package that talks to
OpenSearch/DuckDB - brand.py stays pure and testable without a live cluster.
"""

from __future__ import annotations

from opensearchpy import OpenSearch

from er.config import AppConfig
from er.family.brand import classify_tier, extract_brand_core, guess_role
from er.family.models import FamilyMember, FamilyResult, RelationshipEvidence
from er.graph.edges import fetch_relationships_among
from er.retrieval.candidates import search_candidates


def discover_family(client: OpenSearch, cfg: AppConfig, name: str, country: str | None = None) -> FamilyResult:
    brand_core = extract_brand_core(name)

    raw_candidates = search_candidates(
        client, cfg, brand_core, country, size=cfg.family.candidate_pool_size
    )

    members: list[FamilyMember] = []
    by_lei: dict[str, dict] = {}
    for c in raw_candidates:
        candidate_core = extract_brand_core(c["legal_name"])
        tier = classify_tier(brand_core, candidate_core)
        if tier is None:
            continue
        members.append(
            FamilyMember(
                lei=c["lei"],
                legal_name=c["legal_name"],
                jurisdiction=c.get("jurisdiction"),
                role=guess_role(c),
                confidence=tier,
            )
        )
        by_lei[c["lei"]] = c

    edges = fetch_relationships_among(cfg, list(by_lei.keys()))
    confirmed_leis: set[str] = set()
    evidence: list[RelationshipEvidence] = []
    for e in edges:
        confirmed_leis.add(e["start_node_id"])
        confirmed_leis.add(e["end_node_id"])
        evidence.append(
            RelationshipEvidence(
                from_lei=e["start_node_id"],
                from_name=by_lei[e["start_node_id"]]["legal_name"],
                relationship_type=e["relationship_type"],
                to_lei=e["end_node_id"],
                to_name=by_lei[e["end_node_id"]]["legal_name"],
            )
        )

    for member in members:
        if member.lei in confirmed_leis:
            member.graph_confirmed = True

    return FamilyResult(query_name=name, brand_core=brand_core, members=members, relationship_evidence=evidence)
