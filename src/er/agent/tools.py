"""Tool implementations backing er.agent.mcp_server. Each function wraps
*existing* core logic completely unchanged (er.entity.search,
er.entity.profile, er.graph.build) - this module adds no entity-resolution
logic of its own, same rule as er.api.app and er.cli. Its only addition is
constructing deterministic Evidence records alongside the data for every
call, so a consumer (er.agent.orchestrator, or any other MCP client) can cite
exactly what was looked up rather than the model asserting an answer.
"""

from __future__ import annotations

import hashlib
import uuid

from er.config import AppConfig
from er.entity.profile import get_entity_profile
from er.entity.search import match_result_to_matches, search_by_cusip, search_by_lei, search_by_name
from er.graph.build import build_hierarchy_tree
from er.graph.models import HierarchyNode

from .models import Evidence, ToolResult


def _evidence_id() -> str:
    return f"ev_{uuid.uuid4().hex[:10]}"


def _query_hash(tool_name: str, **kwargs: object) -> str:
    payload = f"{tool_name}:" + ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def search_entity(
    cfg: AppConfig, query: str, search_type: str = "name", country: str | None = None
) -> ToolResult:
    """Search for an entity by name, LEI, or CUSIP. Returns candidate entities
    with their entity_id (LEI) - pass that entity_id to get_entity_profile or
    get_relationship_hierarchy for detail. search_type must be one of "name",
    "lei", "cusip"."""
    qh = _query_hash("search_entity", query=query, search_type=search_type, country=country)

    if search_type == "lei":
        lei = query.strip().upper()
        matches = search_by_lei(cfg, lei)
        source = "GLEIF entity record (exact LEI lookup)"
        criteria = [f"Entity ID = {lei}"]
        fact_type: str = "lookup"
    elif search_type == "cusip":
        cusip = query.strip().upper()
        matches = search_by_cusip(cfg, cusip)
        source = "SEC 13F holdings crosswalked to GLEIF"
        criteria = [f"CUSIP = {cusip}"]
        fact_type = "lookup"
    elif search_type == "name":
        result = search_by_name(cfg, query, country)
        matches = match_result_to_matches(result)
        source = "OpenSearch candidate retrieval + deterministic matching (er.matching.matcher)"
        criteria = [f'Query name = "{query}"']
        if country:
            criteria.append(f"Country = {country}")
        criteria.append(f"Matcher decision = {result.decision.value}")
        fact_type = "search_match"
    else:
        raise ValueError(f'search_type must be one of "name", "lei", "cusip"; got {search_type!r}')

    evidence = [
        Evidence(
            evidence_id=_evidence_id(),
            source=source,
            fact_type=fact_type,  # type: ignore[arg-type]
            criteria=criteria,
            record_refs=[m.entity_id for m in matches],
            fields_used=["canonical_name", "jurisdiction", "legal_country"],
            result_count=len(matches),
            query_hash=qh,
        )
    ]
    return ToolResult(data={"matches": [m.model_dump() for m in matches]}, evidence=evidence)


def get_entity_profile_tool(cfg: AppConfig, entity_id: str) -> ToolResult:
    """Get an entity's full profile: identity, GLEIF registration lineage,
    every attached identifier (LEI/CIK/ISIN/...) with its source, and latest
    SEC 13F filing activity if it is a resolved 13F filer."""
    qh = _query_hash("get_entity_profile", entity_id=entity_id)
    profile = get_entity_profile(cfg, entity_id)
    if profile is None:
        return ToolResult(
            data={"found": False},
            evidence=[
                Evidence(
                    evidence_id=_evidence_id(),
                    source="GLEIF entity record",
                    fact_type="lookup",
                    criteria=[f"Entity ID = {entity_id}"],
                    record_refs=[entity_id],
                    result_count=0,
                    query_hash=qh,
                    warnings=["No canonical entity found for this entity_id."],
                )
            ],
        )

    evidence = [
        Evidence(
            evidence_id=_evidence_id(),
            source="GLEIF entity record",
            source_timestamp=profile.lineage.gleif_snapshot_date if profile.lineage else None,
            fact_type="lookup",
            criteria=[f"Entity ID = {entity_id}"],
            record_refs=[entity_id],
            fields_used=["canonical_name", "entity_type", "jurisdiction", "legal_country", "entity_status"],
            result_count=1,
            query_hash=qh,
        )
    ]
    if profile.lineage:
        evidence.append(
            Evidence(
                evidence_id=_evidence_id(),
                source="GLEIF registration lineage",
                source_timestamp=profile.lineage.gleif_snapshot_date,
                fact_type="lookup",
                criteria=[f"Entity ID = {entity_id}"],
                record_refs=[entity_id],
                fields_used=[
                    "entity_creation_date",
                    "initial_registration_date",
                    "last_update_date",
                    "next_renewal_date",
                    "registration_status",
                ],
                result_count=1,
                query_hash=qh,
            )
        )
    if profile.identifiers:
        evidence.append(
            Evidence(
                evidence_id=_evidence_id(),
                source="Attached source identifiers",
                fact_type="records",
                criteria=[f"Entity ID = {entity_id}"],
                record_refs=[entity_id],
                fields_used=["identifier_type", "identifier_value", "source", "snapshot_date"],
                result_count=len(profile.identifiers),
                query_hash=qh,
            )
        )
    if profile.sec_13f:
        evidence.append(
            Evidence(
                evidence_id=_evidence_id(),
                source="SEC 13F filing",
                source_timestamp=profile.sec_13f.latest_filing_date,
                fact_type="lookup",
                criteria=[f"CIK = {profile.sec_13f.cik}"],
                record_refs=[profile.sec_13f.cik],
                fields_used=[
                    "latest_period_of_report",
                    "latest_filing_date",
                    "reported_security_count",
                    "top_reported_holdings",
                ],
                result_count=profile.sec_13f.reported_security_count,
                query_hash=qh,
                warnings=[
                    "Latest reported 13F holdings only - excludes short positions, derivatives, "
                    "non-US securities, private investments and sub-threshold positions."
                ],
            )
        )

    return ToolResult(data={"found": True, "profile": profile.model_dump()}, evidence=evidence)


def _count_nodes(node: HierarchyNode) -> int:
    return 1 + sum(_count_nodes(c) for c in node.upward) + sum(_count_nodes(c) for c in node.downward)


def get_relationship_hierarchy(
    cfg: AppConfig, entity_id: str, depth: int = 2, direction: str = "all"
) -> ToolResult:
    """Get an entity's GLEIF relationship neighborhood: parents/managers
    upward, subsidiaries/funds downward, up to `depth` hops. direction must be
    one of "all", "parents", "children"."""
    qh = _query_hash("get_relationship_hierarchy", entity_id=entity_id, depth=depth, direction=direction)
    root = build_hierarchy_tree(cfg, entity_id, depth=depth, direction=direction)

    evidence = [
        Evidence(
            evidence_id=_evidence_id(),
            source="GLEIF relationship/exception records",
            fact_type="records",
            criteria=[f"Entity ID = {entity_id}", f"Depth = {depth}", f"Direction = {direction}"],
            record_refs=[entity_id],
            fields_used=["relationship_type", "label", "status"],
            result_count=_count_nodes(root),
            query_hash=qh,
        )
    ]
    return ToolResult(data={"tree": root.model_dump()}, evidence=evidence)
