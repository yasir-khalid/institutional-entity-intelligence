"""FastAPI backend for the web frontend (see web/).

This is a thin translation layer, same principle as er.cli: it owns no
entity-resolution logic itself, only HTTP wiring and JSON shaping (schemas.py).
Every real operation is delegated to the existing core packages -
er.matching.matcher, er.graph.build, er.entity.profile - unchanged, so the web
frontend and the terminal CLIs are two views over the exact same logic, never
two implementations of it.

Run: `make api` (or `uv run uvicorn er.api.app:app --reload --port 8000`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from mcp import Client

from er.agent.models import AskResult as AgentAskResult
from er.agent.orchestrator import ask as agent_ask
from er.agent.orchestrator import mcp_stdio_params
from er.api.schemas import (
    AskRequest,
    AskResponse,
    CitationOut,
    EntityConnectionsOut,
    EntityDetail,
    EntityIdentifierOut,
    EntityLineageOut,
    DerivationOut,
    EvidenceOut,
    FactOut,
    MatchDecisionOut,
    MatchReviewOut,
    NPortFundReportOut,
    ReviewRequest,
    Sec13FActivityOut,
    Sec13FHoldingOut,
    SearchResponse,
    SearchResult,
    ToolResultOut,
    TreeNode,
    VerificationOut,
)
from er.config import AppConfig, load_config
from er.datasources.sec_adv.search import load_document
from er.agent.tools import get_position_history
from er.entity.connections import load_connections
from er.entity.profile import get_entity_profile
from er.entity.resolution import load_match_decisions, record_review
from er.entity.search import match_result_to_matches, search_by_cusip, search_by_lei, search_by_name
from er.graph.build import build_hierarchy_tree
from er.graph.models import HierarchyNode
from er.serving.store import MissingIndexError, get_store

logger = logging.getLogger(__name__)


def _cfg() -> AppConfig:
    # Re-loaded per call rather than cached at import time - load_config()
    # itself is lru_cache'd (er.config), so this is cheap and keeps the module
    # free of import-time side effects.
    return load_config()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The entity-intelligence MCP server (er.agent.mcp_server) is spawned once
    # as a subprocess here and kept connected for the app's lifetime - see
    # er.agent.orchestrator for why /api/ask is a real MCP client talking to a
    # real MCP server, not a direct Python import of its tools. A startup
    # failure here (e.g. the subprocess command isn't on PATH) must not take
    # down search/tree/detail, which don't depend on it - only /api/ask does.
    app.state.mcp_client = None
    try:
        client = Client(mcp_stdio_params(_cfg()))
        await client.__aenter__()
        app.state.mcp_client = client
    except Exception:
        logger.exception("Could not start the entity-intelligence MCP server - /api/ask will be unavailable")
    yield
    if app.state.mcp_client is not None:
        await app.state.mcp_client.__aexit__(None, None, None)


app = FastAPI(title="Institutional Entity Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Any localhost port, not just 3000 - Next.js picks the next free port when
    # 3000 is taken by another project. This API has no auth yet, so it must
    # never be exposed to non-localhost origins as-is.
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)



@app.exception_handler(MissingIndexError)
async def missing_index(_: Request, exc: MissingIndexError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


SEARCH_TYPES = ("name", "lei", "cusip")


def _search_by_lei(cfg: AppConfig, lei: str) -> list[SearchResult]:
    return [SearchResult(**m.model_dump()) for m in search_by_lei(get_store(cfg), lei)]


def _search_by_cusip(cfg: AppConfig, cusip: str) -> list[SearchResult]:
    return [SearchResult(**m.model_dump()) for m in search_by_cusip(get_store(cfg), cusip)]


def _search_by_name(cfg: AppConfig, name: str, country: str | None) -> list[SearchResult]:
    result = search_by_name(cfg, name, country)
    return [SearchResult(**m.model_dump()) for m in match_result_to_matches(result)]


@app.get("/api/search", response_model=SearchResponse)
def search(
    query: str = Query(..., min_length=1),
    search_type: str = Query("name"),
    country: str | None = None,
) -> SearchResponse:
    if search_type not in SEARCH_TYPES:
        raise HTTPException(400, f"search_type must be one of {SEARCH_TYPES}")

    cfg = _cfg()
    if search_type == "lei":
        results = _search_by_lei(cfg, query.strip().upper())
    elif search_type == "cusip":
        results = _search_by_cusip(cfg, query.strip().upper())
    else:
        results = _search_by_name(cfg, query, country)

    return SearchResponse(query=query, search_type=search_type, results=results)


def _convert_tree(node: HierarchyNode, direction: str | None) -> TreeNode:
    children = [_convert_tree(c, "upward") for c in node.upward] + [
        _convert_tree(c, "downward") for c in node.downward
    ]
    return TreeNode(
        entity_id=node.lei,
        name=node.name,
        direction=direction,
        relationship_type=node.relationship_type,
        label=node.label,
        expanded=node.expanded,
        children=children,
    )


@app.get("/api/entity/{entity_id}/tree", response_model=TreeNode)
def entity_tree(
    entity_id: str,
    depth: int = Query(2, ge=1, le=5),
    direction: str = Query("all"),
    extra_parent_depth: int = Query(
        1, ge=0, le=3, description="Extra hops upward beyond depth - ownership chains are usually short and high-value to see in full."
    ),
    max_nodes: int = Query(
        30,
        ge=10,
        le=100,
        description=(
            "Caps how many entities get their own relationships expanded (not the total tree "
            "size, which can still exceed this - each expansion can list many un-expanded leaf "
            "children). This budget vs. total-node-count relationship is highly non-linear for "
            "hub-heavy entities (confirmed live on one real entity: max_nodes=35 -> 48 total "
            "nodes, max_nodes=40 -> 434, max_nodes=55 -> 1,111 - one extra hub expansion can "
            "unlock a cascade), so this default is chosen to sit safely below where that specific "
            "cascade started, not simply scaled down from build_hierarchy_tree's own CLI default "
            "(200, fine for a single terminal render, unsafe for a DOM-per-node web tree)."
        ),
    ),
) -> TreeNode:
    if direction not in ("parents", "children", "all"):
        raise HTTPException(400, "direction must be one of parents, children, all")
    root = build_hierarchy_tree(
        get_store(_cfg()),
        entity_id,
        depth=depth,
        direction=direction,
        extra_parent_depth=extra_parent_depth,
        max_nodes=max_nodes,
    )
    return _convert_tree(root, None)


@app.get("/api/entity/{entity_id}", response_model=EntityDetail)
def entity_detail(entity_id: str) -> EntityDetail:
    store = get_store(_cfg())
    profile = get_entity_profile(store, entity_id)
    if profile is None:
        raise HTTPException(404, f"no canonical entity found for {entity_id}")

    sec = profile.sec_13f
    return EntityDetail(
        entity_id=profile.entity_id,
        canonical_name=profile.canonical_name,
        entity_type=profile.entity_type,
        jurisdiction=profile.jurisdiction,
        legal_country=profile.legal_country,
        entity_status=profile.entity_status,
        lineage=(
            EntityLineageOut(
                entity_creation_date=profile.lineage.entity_creation_date,
                initial_registration_date=profile.lineage.initial_registration_date,
                last_update_date=profile.lineage.last_update_date,
                next_renewal_date=profile.lineage.next_renewal_date,
                registration_status=profile.lineage.registration_status,
                gleif_snapshot_date=profile.lineage.gleif_snapshot_date,
            )
            if profile.lineage
            else None
        ),
        identifiers=[
            EntityIdentifierOut(
                identifier_type=i.identifier_type,
                identifier_value=i.identifier_value,
                confidence=i.confidence,
                source=i.source,
                source_file=i.source_file,
                snapshot_date=i.snapshot_date,
                ingested_at=i.ingested_at,
            )
            for i in profile.identifiers
        ],
        sec_13f=(
            Sec13FActivityOut(
                cik=sec.cik,
                latest_period_of_report=sec.latest_period_of_report,
                latest_filing_date=sec.latest_filing_date,
                reported_security_count=sec.reported_security_count,
                value_unit=sec.value_unit,
                top_reported_holdings=[
                    Sec13FHoldingOut(name_of_issuer=h.name_of_issuer, value=h.value, cusip=h.cusip)
                    for h in sec.top_reported_holdings
                ],
                quarantined_filings=sec.quarantined_filings,
                scale_suspect_filings=sec.scale_suspect_filings,
            )
            if sec
            else None
        ),
        nport=NPortFundReportOut(**profile.nport.model_dump()) if profile.nport else None,
        parent_count=len(profile.hierarchy.upward) if profile.hierarchy else 0,
        subsidiary_count=len(profile.hierarchy.downward) if profile.hierarchy else 0,
        identifier_total=profile.identifier_total,
        connections=EntityConnectionsOut(**load_connections(store, entity_id).model_dump()),
        match_decisions=[MatchDecisionOut(**d.model_dump()) for d in load_match_decisions(store, entity_id)],
    )


@app.get("/api/positions/{cik}/{cusip}", response_model=ToolResultOut)
def position_history(cik: str, cusip: str, periods: int = Query(4, ge=2, le=8)) -> ToolResultOut:
    """The same deterministic result the agent's get_position_history tool
    returns: period totals and changes as derived facts, each with its formula
    and input rows."""
    result = get_position_history(get_store(_cfg()), cik, cusip, periods=periods)
    return ToolResultOut(**result.model_dump())


@app.post("/api/reviews", response_model=MatchReviewOut)
def add_review(body: ReviewRequest) -> MatchReviewOut:
    """Appends a human review of a match. It takes effect in the graph on the
    next `make build-knowledge-graph`; the entity view shows it immediately."""
    try:
        review = record_review(get_store(_cfg()), body.node_id, body.lei, body.outcome, body.reviewer, body.rationale)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return MatchReviewOut(**review.model_dump())


@app.get("/api/sources/sec-adv/{pdf_file_name}")
def sec_adv_document(pdf_file_name: str) -> Response:
    content = load_document(_cfg(), get_store(_cfg()), pdf_file_name)
    if content is None:
        raise HTTPException(404, "SEC Form ADV brochure not found")
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_file_name}"'},
    )


def _verification_out(result: AgentAskResult) -> VerificationOut | None:
    """Project er.agent.verifier's badge for the wire. `usage` (token counts and
    cost) is deliberately dropped here - it is operator telemetry, not something
    the UI should show next to an answer."""
    if result.verification is None:
        return None
    return VerificationOut(**result.verification.model_dump(exclude={"usage"}))


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(body: AskRequest) -> AskResponse:
    """Answer a question about an entity via er.agent.orchestrator, which
    drives an OpenRouter model through the MCP tools in er.agent.mcp_server
    (started once at app startup - see `lifespan` above) and returns an
    answer with citations to the Evidence records those tool calls produced."""
    client = app.state.mcp_client
    if client is None:
        raise HTTPException(503, "The entity-intelligence agent is unavailable (its MCP server failed to start).")
    try:
        result = await agent_ask(
            client, _cfg(), body.question, body.entity_id, history=[turn.model_dump() for turn in body.history]
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(marker=c.marker, evidence_id=c.evidence_id) for c in result.citations],
        evidence={k: EvidenceOut(**v.model_dump()) for k, v in result.evidence.items()},
        facts={k: FactOut(**v.model_dump()) for k, v in result.facts.items()},
        derivations={k: DerivationOut(**v.model_dump()) for k, v in result.derivations.items()},
        verification=_verification_out(result),
    )


@app.post("/api/ask/stream")
async def ask_question_stream(body: AskRequest) -> StreamingResponse:
    """Same answer as /api/ask, but streamed as Server-Sent Events so the UI can
    show what the agent is doing (which tool it called, what came back) while it
    runs instead of a blank spinner. Each SSE `data:` line is one JSON event;
    the final event has type "answer" and carries the same shape as
    /api/ask's response, or type "error" if the run failed. With `trace: true`
    in the body, "trace" events carrying developer spans are interleaved too
    (see er.agent.trace)."""
    client = app.state.mcp_client
    if client is None:
        raise HTTPException(503, "The entity-intelligence agent is unavailable (its MCP server failed to start).")

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            result = await agent_ask(
                client,
                _cfg(),
                body.question,
                body.entity_id,
                history=[turn.model_dump() for turn in body.history],
                on_event=on_event,
                trace=body.trace,
            )
            verification = _verification_out(result)
            await queue.put(
                {
                    "type": "answer",
                    "answer": result.answer,
                    "citations": [c.model_dump() for c in result.citations],
                    "evidence": {k: v.model_dump() for k, v in result.evidence.items()},
                    "facts": {k: v.model_dump() for k, v in result.facts.items()},
                    "derivations": {k: v.model_dump() for k, v in result.derivations.items()},
                    "verification": verification.model_dump() if verification else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error event
            logger.exception("streamed ask failed")
            # httpx timeouts stringify to "", which left the UI with a blank error.
            await queue.put({"type": "error", "message": str(exc) or type(exc).__name__})
        finally:
            await queue.put(None)

    async def event_stream() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
