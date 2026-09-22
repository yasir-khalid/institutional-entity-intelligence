"""Entity search across the three lookup modes the product supports: exact LEI
lookup, CUSIP-via-13F-crosswalk lookup, and fuzzy name matching. This logic
used to live inline as private helpers in er.api.app; it moved here so a
second consumer (er.agent.tools, for the MCP/agent Q&A surface) doesn't need
to reimplement it - same principle as er.crosswalk calling
er.matching.matcher.match() unchanged rather than duplicating matching logic
per source. er.api.app now imports these and only shapes the HTTP response.
"""

from __future__ import annotations

import duckdb
from pydantic import BaseModel

from er.config import AppConfig
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match
from er.matching.models import MatchResult


class EntityMatch(BaseModel):
    """One candidate entity produced by a search, independent of transport -
    field names deliberately mirror er.api.schemas.SearchResult so callers on
    either side (HTTP, MCP tool) can convert with a plain field-for-field copy."""

    entity_id: str
    canonical_name: str
    jurisdiction: str | None = None
    legal_country: str | None = None
    decision: str | None = None  # AUTO_MATCH/REVIEW/UNMATCHED for name search; None for direct LEI/CUSIP lookups
    score: float | None = None
    matched_via: str  # "name" | "lei" | "cusip"
    cik: str | None = None  # populated for cusip search - which filer reported holding it


def search_by_lei(cfg: AppConfig, lei: str) -> list[EntityMatch]:
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
        EntityMatch(
            entity_id=row[0], canonical_name=row[1], jurisdiction=row[2], legal_country=row[3], matched_via="lei"
        )
    ]


def search_by_cusip(cfg: AppConfig, cusip: str) -> list[EntityMatch]:
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
        EntityMatch(
            entity_id=lei or f"unresolved-cik-{cik}",
            canonical_name=filer_name,
            decision=decision,
            matched_via="cusip",
            cik=cik,
        )
        for filer_name, cik, lei, decision in rows
    ]


def search_by_name(cfg: AppConfig, name: str, country: str | None) -> MatchResult:
    """Returns the full MatchResult (not just top candidates) so a caller that
    wants the matcher's own decision/gap/reason - e.g. the agent, to explain a
    REVIEW/UNMATCHED outcome as evidence rather than silently picking the top
    candidate - has it. Use match_result_to_matches() for the flattened list."""
    client = get_client(cfg)
    return match(client, cfg, name, country)


def match_result_to_matches(result: MatchResult, limit: int = 10) -> list[EntityMatch]:
    return [
        EntityMatch(
            entity_id=c.lei,
            canonical_name=c.legal_name,
            jurisdiction=c.jurisdiction,
            decision=result.decision.value if c.lei == result.lei else None,
            score=c.score,
            matched_via="name",
        )
        for c in result.candidates[:limit]
    ]
