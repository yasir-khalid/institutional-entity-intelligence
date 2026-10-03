"""Entity search across the three lookup modes the product supports: exact LEI
lookup, CUSIP-via-13F-crosswalk lookup, and fuzzy name matching. This logic
used to live inline as private helpers in er.api.app; it moved here so a
second consumer (er.agent.tools, for the MCP/agent Q&A surface) doesn't need
to reimplement it - same principle as er.crosswalk calling
er.matching.matcher.match() unchanged rather than duplicating matching logic
per source. er.api.app now imports these and only shapes the HTTP response.
"""

from __future__ import annotations

from pydantic import BaseModel

from er.config import AppConfig
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match
from er.matching.models import MatchResult
from er.serving.store import ENTITIES, FILERS, HOLDINGS, Store


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


def search_by_lei(store: Store, lei: str) -> list[EntityMatch]:
    doc = store.get(ENTITIES, lei, fields=("entity_id", "canonical_name", "jurisdiction", "legal_country"))
    if doc is None:
        return []
    return [
        EntityMatch(
            entity_id=doc["entity_id"],
            canonical_name=doc["canonical_name"],
            jurisdiction=doc.get("jurisdiction"),
            legal_country=doc.get("legal_country"),
            matched_via="lei",
        )
    ]


def search_by_cusip(store: Store, cusip: str) -> list[EntityMatch]:
    """13F filers that reported a position in this CUSIP, resolved to their
    LEI where the crosswalk found one."""
    holders = store.find(HOLDINGS, where={"cusip": cusip}, collapse="cik", size=25, fields=("cik",))
    filers = store.mget(FILERS, [holder["cik"] for holder in holders], fields=("filer_name", "lei", "decision"))
    return [
        EntityMatch(
            entity_id=filers.get(holder["cik"], {}).get("lei") or f"unresolved-cik-{holder['cik']}",
            canonical_name=filers.get(holder["cik"], {}).get("filer_name") or holder["cik"],
            decision=filers.get(holder["cik"], {}).get("decision"),
            matched_via="cusip",
            cik=holder["cik"],
        )
        for holder in holders
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
