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
    fact_type: Literal["lookup", "search_match", "records"]
    criteria: list[str] = []
    record_refs: list[str] = []
    fields_used: list[str] = []
    result_count: int | None = None
    query_hash: str
    warnings: list[str] = []


class ToolResult(BaseModel):
    """What every er.agent tool returns over MCP: the answer-relevant data,
    plus the Evidence record(s) substantiating it. `data` is deliberately a
    plain dict (not a typed model) - each tool's shape differs and the model
    only ever sees this serialized as its tool-call result."""

    data: dict[str, Any]
    evidence: list[Evidence] = []


class Citation(BaseModel):
    marker: int
    evidence_id: str


class AskResult(BaseModel):
    answer: str
    citations: list[Citation] = []
    evidence: dict[str, Evidence] = {}
