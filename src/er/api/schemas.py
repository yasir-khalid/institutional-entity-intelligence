"""JSON response shapes for the web API - deliberately separate from
er.matching.models/er.graph.models/er.entity.models (the internal domain
models): this module's job is only to shape data for the frontend, the same
way er.cli.entity_render's job is only to shape data for a terminal. Core
logic never imports this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    cusip: str | None = None


class Sec13FActivityOut(BaseModel):
    cik: str
    latest_period_of_report: str | None = None
    latest_filing_date: str | None = None
    reported_security_count: int = 0
    value_unit: str = "USD"
    top_reported_holdings: list[Sec13FHoldingOut] = []
    quarantined_filings: list[str] = []
    scale_suspect_filings: list[str] = []


class NPortHoldingOut(BaseModel):
    holding_id: str
    issuer_name: str | None = None
    issuer_lei: str | None = None
    cusip: str | None = None
    isin: str | None = None
    asset_category: str | None = None
    payoff_profile: str | None = None
    value_usd: float | None = None
    percentage: float | None = None


class NPortFundReportOut(BaseModel):
    series_lei: str
    series_id: str | None = None
    series_name: str | None = None
    cik: str | None = None
    registrant_name: str | None = None
    accession_number: str
    report_date: str | None = None
    filing_date: str | None = None
    net_assets: float | None = None
    total_assets: float | None = None
    holding_count: int = 0
    top_holdings: list[NPortHoldingOut] = []


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
    source_uri: str | None = None
    page: int | None = None


class FactAddressOut(BaseModel):
    source: str
    document_id: str
    snapshot_id: str | None = None
    locator: str
    field: str
    uri: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class FactOut(BaseModel):
    """One addressed value an answer stated - see er.agent.models.Fact."""

    fact_id: str
    evidence_id: str
    subject: str
    predicate: str
    value: str | int | float | bool | None
    unit: str | None = None
    as_of: str | None = None
    address: FactAddressOut


class DerivationOut(BaseModel):
    fact_id: str
    formula_id: str
    expression: str
    inputs: list[str]


class ToolResultOut(BaseModel):
    """A deterministic tool result served straight to the UI (no model in the
    loop): its data plus the evidence, facts and derivations behind it."""

    data: dict
    evidence: list[EvidenceOut] = []
    facts: list[FactOut] = []
    derivations: list[DerivationOut] = []


class CitationOut(BaseModel):
    marker: int
    evidence_id: str


class ConversationTurn(BaseModel):
    """Prior text from this browser conversation, supplied as context only.

    It intentionally carries no evidence IDs or tool payloads: every new agent
    answer must still gather and cite evidence produced during its own run.
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class AskRequest(BaseModel):
    question: str
    entity_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=8)
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
    facts: dict[str, FactOut] = {}
    derivations: dict[str, DerivationOut] = {}
    verification: VerificationOut | None = None


class LinkedRecordOut(BaseModel):
    node_id: str
    display_name: str | None = None
    source: str


class ConnectionOut(BaseModel):
    edge_type: str
    direction: str
    other_node_id: str
    other_name: str | None = None
    other_type: str | None = None
    source: str
    valid_from: str | None = None
    valid_to: str | None = None
    percent: float | None = None
    source_url: str | None = None


class ConnectionGroupOut(BaseModel):
    edge_type: str
    direction: str
    total: int
    connections: list[ConnectionOut]


class EntityConnectionsOut(BaseModel):
    linked_records: list[LinkedRecordOut] = []
    groups: list[ConnectionGroupOut] = []


class MatchReviewOut(BaseModel):
    node_id: str
    lei: str
    outcome: str
    reviewer: str
    reviewed_at: str
    rationale: str | None = None


class MatchDecisionOut(BaseModel):
    node_id: str
    source_name: str | None = None
    lei: str | None = None
    decision: str
    score: float | None = None
    gap: float | None = None
    reason: str | None = None
    runner_up_lei: str | None = None
    runner_up_name: str | None = None
    runner_up_score: float | None = None
    feature_contributions: dict[str, float] = {}
    config_hash: str | None = None
    decided_on: str | None = None
    reviews: list[MatchReviewOut] = []


class ReviewRequest(BaseModel):
    node_id: str
    lei: str
    outcome: str
    reviewer: str
    rationale: str | None = None


class EntityDetail(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str | None = None
    jurisdiction: str | None = None
    legal_country: str | None = None
    entity_status: str | None = None
    lineage: EntityLineageOut | None = None
    identifiers: list[EntityIdentifierOut] = []
    identifier_total: int = 0
    sec_13f: Sec13FActivityOut | None = None
    nport: NPortFundReportOut | None = None
    parent_count: int = 0
    subsidiary_count: int = 0
    connections: EntityConnectionsOut = EntityConnectionsOut()
    match_decisions: list[MatchDecisionOut] = []
