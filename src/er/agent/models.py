"""The Evidence contract shared by every er.agent tool and consumed by
er.agent.orchestrator, the FastAPI /api/ask endpoint, and the web "Evidence
layer" panel.

This is deliberately not RAG-style text chunks - there is no document corpus
here, the underlying data comes from OpenSearch/DuckDB lookups over
Parquet - so instead each tool call constructs a deterministic provenance
record for what it looked up: which source, what criteria, how many records,
as of when, and a reproducible query hash. The LLM never invents this data or
a confidence score; it only cites evidence_ids that a tool call actually
returned in the same conversation (enforced in er.agent.orchestrator).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class Evidence(BaseModel):
    evidence_id: str
    source: str
    source_timestamp: str | None = None
    fact_type: Literal["lookup", "search_match", "records", "derivation"]
    criteria: list[str] = []
    record_refs: list[str] = []
    fields_used: list[str] = []
    result_count: int | None = None
    query_hash: str
    warnings: list[str] = []
    source_uri: str | None = None
    page: int | None = None


class FactAddress(BaseModel):
    source: str
    document_id: str
    snapshot_id: str | None = None
    locator: str
    field: str
    uri: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class Fact(BaseModel):
    fact_id: str
    evidence_id: str
    subject: str
    predicate: str
    value: str | int | float | bool | None
    unit: str | None = None
    as_of: str | None = None
    address: FactAddress


class Derivation(BaseModel):
    """How a derived fact was computed: a registered formula (er.knowledge.formulas)
    applied to other facts, each of which keeps its own source address."""

    fact_id: str
    formula_id: str
    expression: str
    inputs: list[str]


class ToolResult(BaseModel):
    """What every er.agent tool returns over MCP: the answer-relevant data,
    plus the Evidence record(s) substantiating it. `data` is deliberately a
    plain dict (not a typed model) - each tool's shape differs and the model
    only ever sees this serialized as its tool-call result."""

    data: dict[str, Any]
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    derivations: list[Derivation] = []


class Citation(BaseModel):
    marker: int
    evidence_id: str


class VerificationCheck(BaseModel):
    """One typed question Jev answered about the finished answer. `probability`
    is Jev's calibrated probability that the check holds (1.0 = holds); it is
    None when the model did not return that key at all, which is "no signal"
    and must not be read as a failure - so `passed` is None too, never False.
    """

    key: str
    label: str
    probability: float | None = None
    threshold: float
    passed: bool | None = None


class Verification(BaseModel):
    """The verification badge attached to an AskResult - see er.agent.verifier.

    "unavailable" means the check did not run (verifier disabled, model
    unreachable, unparseable response) and is deliberately distinct from
    "unverified", which means it ran and the answer did not hold up. A consumer
    must not render the two the same way.
    """

    status: Literal["verified", "partial", "unverified", "unavailable"]
    headline: str
    detail: str
    model: str | None = None
    checks: list[VerificationCheck] = []
    verdict: str | None = None
    verdict_confidence: float | None = None
    latency_ms: int | None = None
    # How many Decisions calls it took (er.agent.verifier retries transient
    # failures). Developer-trace detail; not part of the API's badge shape.
    attempts: int | None = None
    usage: dict[str, Any] | None = None
    reason: str | None = None


class AskResult(BaseModel):
    answer: str
    citations: list[Citation] = []
    evidence: dict[str, Evidence] = {}
    # The facts whose placeholders the answer used, as they were re-checked at
    # submission - what the hard-path evaluation (er.evaluation.agent_eval) scores.
    facts: dict[str, Fact] = {}
    # How each derived fact in `facts` was computed, and the input facts it
    # needs (included in `facts` too, so every input can be shown).
    derivations: dict[str, Derivation] = {}
    verification: Verification | None = None
