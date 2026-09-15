from __future__ import annotations

from pydantic import BaseModel

from er.graph.models import HierarchyResult


class EntityIdentifier(BaseModel):
    """One external identifier attached to a canonical entity by some source -
    e.g. a SEC CIK from the sec_13f crosswalk, an ISIN from GLEIF's own bridge.
    `confidence` carries whatever the source's own resolution process produced
    (a matcher Decision like AUTO_MATCH/REVIEW, or "SOURCE" for an identifier
    that came directly from a source's own authoritative data with no matching
    step involved, e.g. GLEIF's ISIN bridge).

    source_file/snapshot_date/ingested_at are provenance, carried through
    unchanged from whichever raw file/crosswalk run produced this identifier
    (er.datasources.common.parquet_writer.PROVENANCE_FIELDS) - answers "where
    did this come from, and as of when," not just "what is it."
    """

    identifier_type: str
    identifier_value: str
    confidence: str
    source: str
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class Sec13FHoldingSummary(BaseModel):
    name_of_issuer: str
    value: int | None = None


class Sec13FActivity(BaseModel):
    """Summary of one entity's most recent SEC Form 13F filing - NOT its complete
    portfolio. 13F only covers certain reportable US equity securities as of one
    quarterly date; it excludes shorts, derivatives, non-US securities, private
    investments, and positions below reporting thresholds. Always render this as
    "latest reported holdings," never as "holdings" or "portfolio" unqualified."""

    cik: str
    latest_period_of_report: str | None = None
    latest_filing_date: str | None = None
    reported_security_count: int = 0
    top_reported_holdings: list[Sec13FHoldingSummary] = []


class EntityLineage(BaseModel):
    """GLEIF's own identity timeline for this entity - when it was created,
    first registered, last updated, and next due for renewal, plus its
    registration_status (e.g. ISSUED vs PENDING_VALIDATION). This data has
    been sitting in gleif_entities.parquet since Phase 2 but never reached
    the canonical entity layer or any consumer (CLI or API) before now -
    "entity identity, lineage, provenance" is durable, high-value data that
    deserves to actually be visible, not just captured at ingestion time."""

    entity_creation_date: str | None = None
    initial_registration_date: str | None = None
    last_update_date: str | None = None
    next_renewal_date: str | None = None
    registration_status: str | None = None
    gleif_snapshot_date: str | None = None


class EntityProfile(BaseModel):
    """The single request-level view of a canonical entity - identity, every
    identifier attached to it by any registered source, its GLEIF relationship
    neighborhood, and (when available) its SEC 13F filing activity. This is the
    shape er.cli.entity renders and the shape any future consumer (an API, a
    graph UI) should reuse rather than re-deriving these joins itself."""

    entity_id: str
    canonical_name: str
    entity_type: str | None = None
    jurisdiction: str | None = None
    legal_country: str | None = None
    entity_status: str | None = None
    lineage: EntityLineage | None = None
    identifiers: list[EntityIdentifier] = []
    hierarchy: HierarchyResult | None = None
    sec_13f: Sec13FActivity | None = None
