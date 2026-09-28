"""JSON response shapes for the web API - deliberately separate from
er.matching.models/er.graph.models/er.entity.models (the internal domain
models): this module's job is only to shape data for the frontend, the same
way er.cli.entity_render's job is only to shape data for a terminal. Core
logic never imports this module.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    entity_id: str
    canonical_name: str
    jurisdiction: str | None = None
    legal_country: str | None = None
    decision: str | None = None  # AUTO_MATCH/REVIEW/UNMATCHED for name search; None for direct LEI/CUSIP lookups
    score: float | None = None
    matched_via: str  # "name" | "lei" | "cusip"
    cik: str | None = None  # populated for cusip search - which filer reported holding it


class SearchResponse(BaseModel):
    query: str
    search_type: str
    results: list[SearchResult]


class TreeNode(BaseModel):
    """One node in the rendered relationship tree. `direction` is None only for
    the root (the entity that was searched for) - every other node is reached
    by walking either its upward (parent/manager) or downward (subsidiary/fund)
    edges from its parent in this tree."""

    entity_id: str
    name: str | None
    direction: str | None = None
    relationship_type: str | None = None
    label: str | None = None
    expanded: bool = True
    children: list["TreeNode"] = []


class EntityIdentifierOut(BaseModel):
    identifier_type: str
    identifier_value: str
    confidence: str
    source: str
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class EntityLineageOut(BaseModel):
    entity_creation_date: str | None = None
    initial_registration_date: str | None = None
    last_update_date: str | None = None
    next_renewal_date: str | None = None
    registration_status: str | None = None
    gleif_snapshot_date: str | None = None


class Sec13FHoldingOut(BaseModel):
    name_of_issuer: str
    value: int | None = None


class Sec13FActivityOut(BaseModel):
    cik: str
    latest_period_of_report: str | None = None
    latest_filing_date: str | None = None
    reported_security_count: int = 0
    top_reported_holdings: list[Sec13FHoldingOut] = []


class EvidenceOut(BaseModel):
    evidence_id: str
    source: str
    source_timestamp: str | None = None
    fact_type: str
    criteria: list[str] = []
    record_refs: list[str] = []
    fields_used: list[str] = []
    result_count: int | None = None
    query_hash: str
    warnings: list[str] = []


class CitationOut(BaseModel):
    marker: int
    evidence_id: str


class AskRequest(BaseModel):
    question: str
    entity_id: str | None = None
    # Stream developer trace spans (model turns, tool calls, payloads,
    # timings) alongside the progress events - see er.agent.trace. Only
    # /api/ask/stream honours it; a non-streaming response has nowhere to put
    # a trace.
    trace: bool = False


class VerificationCheckOut(BaseModel):
    key: str
    label: str
    probability: float | None = None
    threshold: float
    passed: bool | None = None


class VerificationOut(BaseModel):
    """The answer's verification badge - see er.agent.verifier. "unavailable"
    (the check did not run) is a different state from "unverified" (it ran and
    the answer did not hold up); the UI must not collapse the two."""

    status: str
    headline: str
    detail: str
    model: str | None = None
    checks: list[VerificationCheckOut] = []
    verdict: str | None = None
    verdict_confidence: float | None = None
    latency_ms: int | None = None
    reason: str | None = None


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    evidence: dict[str, EvidenceOut] = {}
    verification: VerificationOut | None = None


class EntityDetail(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str | None = None
    jurisdiction: str | None = None
    legal_country: str | None = None
    entity_status: str | None = None
    lineage: EntityLineageOut | None = None
    identifiers: list[EntityIdentifierOut] = []
    sec_13f: Sec13FActivityOut | None = None
    parent_count: int = 0
    subsidiary_count: int = 0
