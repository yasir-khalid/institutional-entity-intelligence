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

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from er.api.schemas import (
    EntityDetail,
    EntityIdentifierOut,
    EntityLineageOut,
    Sec13FActivityOut,
    Sec13FHoldingOut,
    SearchResponse,
    SearchResult,
    TreeNode,
)
from er.config import AppConfig, load_config
from er.entity.profile import get_entity_profile
from er.graph.build import build_hierarchy_tree
from er.graph.models import HierarchyNode
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match

app = FastAPI(title="Institutional Entity Intelligence API")

app.add_middleware(
    CORSMiddleware,
    # Any localhost port, not just 3000 - Next.js picks the next free port when
    # 3000 is taken by another project. This API has no auth yet, so it must
    # never be exposed to non-localhost origins as-is.
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET"],
    allow_headers=["*"],
)

SEARCH_TYPES = ("name", "lei", "cusip")


def _cfg() -> AppConfig:
    # Re-loaded per call rather than cached at import time - load_config()
    # itself is lru_cache'd (er.config), so this is cheap and keeps the module
    # free of import-time side effects.
    return load_config()


def _search_by_lei(cfg: AppConfig, lei: str) -> list[SearchResult]:
    path = cfg.entity.processed_dir / "entities.parquet"
    con = duckdb.connect()
    row = con.execute(
        f"SELECT entity_id, canonical_name, jurisdiction, legal_country FROM read_parquet('{path}') WHERE entity_id = ?",
        [lei],
    ).fetchone()
    con.close()
    if not row:
        return []
    return [
        SearchResult(
            entity_id=row[0], canonical_name=row[1], jurisdiction=row[2], legal_country=row[3], matched_via="lei"
        )
    ]


def _search_by_cusip(cfg: AppConfig, cusip: str) -> list[SearchResult]:
    holdings_path = cfg.sec_13f.processed_dir / "sec_13f_holdings.parquet"
    filings_path = cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"
    crosswalk_path = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    if not (holdings_path.exists() and filings_path.exists() and crosswalk_path.exists()):
        return []

    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT DISTINCT f.filer_name, f.cik, x.lei, x.decision
        FROM read_parquet('{holdings_path}') h
        JOIN read_parquet('{filings_path}') f USING (accession_number)
        LEFT JOIN read_parquet('{crosswalk_path}') x USING (cik)
        WHERE h.cusip = ?
        LIMIT 25
        """,
        [cusip],
    ).fetchall()
    con.close()
    return [
        SearchResult(
            entity_id=lei or f"unresolved-cik-{cik}",
            canonical_name=filer_name,
            decision=decision,
            matched_via="cusip",
            cik=cik,
        )
        for filer_name, cik, lei, decision in rows
    ]


def _search_by_name(cfg: AppConfig, name: str, country: str | None) -> list[SearchResult]:
    client = get_client(cfg)
    result = match(client, cfg, name, country)
    return [
        SearchResult(
            entity_id=c.lei,
            canonical_name=c.legal_name,
            jurisdiction=c.jurisdiction,
            decision=result.decision.value if c.lei == result.lei else None,
            score=c.score,
            matched_via="name",
        )
        for c in result.candidates[:10]
    ]


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
        _cfg(),
        entity_id,
        depth=depth,
        direction=direction,
        extra_parent_depth=extra_parent_depth,
        max_nodes=max_nodes,
    )
    return _convert_tree(root, None)


@app.get("/api/entity/{entity_id}", response_model=EntityDetail)
def entity_detail(entity_id: str) -> EntityDetail:
    profile = get_entity_profile(_cfg(), entity_id)
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
                top_reported_holdings=[
                    Sec13FHoldingOut(name_of_issuer=h.name_of_issuer, value=h.value)
                    for h in sec.top_reported_holdings
                ],
            )
            if sec
            else None
        ),
        parent_count=len(profile.hierarchy.upward) if profile.hierarchy else 0,
        subsidiary_count=len(profile.hierarchy.downward) if profile.hierarchy else 0,
    )
