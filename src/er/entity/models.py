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
    cusip: str | None = None


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
    value_unit: str = "USD"
    top_reported_holdings: list[Sec13FHoldingSummary] = []
    # Filings from this filer that failed summary-page reconciliation and were
    # kept out of the holdings ("accession: ERROR, ERROR").
    quarantined_filings: list[str] = []
    # Filings behind the latest period whose implied prices look like
    # thousands (er.datasources.sec_13f.ingest.check_value_scale).
    scale_suspect_filings: list[str] = []


class NPortHoldingSummary(BaseModel):
    holding_id: str
    issuer_name: str | None = None
    issuer_lei: str | None = None
    cusip: str | None = None
    isin: str | None = None
    asset_category: str | None = None
    payoff_profile: str | None = None
    value_usd: float | None = None
    percentage: float | None = None


class NPortFundReport(BaseModel):
    """A registered fund's latest Form N-PORT report, keyed by its series LEI.
    Unlike 13F it covers the whole portfolio - debt, derivatives, non-US and
    short positions included - but it is filed monthly and made public with a
    60-day lag, so it is a dated snapshot, never the current portfolio."""

    series_lei: str
    series_id: str | None = None
    series_name: str | None = None
    cik: str | None = None
    registrant_name: str | None = None
    registrant_lei: str | None = None
    accession_number: str
    report_date: str | None = None
    filing_date: str | None = None
    net_assets: float | None = None
    total_assets: float | None = None
    holding_count: int = 0
    top_holdings: list[NPortHoldingSummary] = []


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
    # All identifiers attached, of which `identifiers` holds up to 200 per type
    # (one issuer carries 650k+ ISINs).
    identifier_total: int = 0
    hierarchy: HierarchyResult | None = None
    sec_13f: Sec13FActivity | None = None
    nport: NPortFundReport | None = None


class LinkedRecord(BaseModel):
    """A record in another source asserted to be this same entity (an SEC CIK,
    an RSSD ID, a Companies House number), and which source asserted it."""

    node_id: str
    display_name: str | None = None
    source: str


class Connection(BaseModel):
    """One typed edge from the knowledge graph. `direction` is from this
    entity's side: "outgoing" means this entity is the edge's subject (it is
    the beneficial owner, the subsidiary, the predecessor)."""

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


class ConnectionGroup(BaseModel):
    edge_type: str
    direction: str
    total: int
    connections: list[Connection]


class EntityConnections(BaseModel):
    linked_records: list[LinkedRecord] = []
    groups: list[ConnectionGroup] = []


class MatchReview(BaseModel):
    node_id: str
    lei: str
    outcome: str
    reviewer: str
    reviewed_at: str
    rationale: str | None = None


class MatchDecisionRecord(BaseModel):
    """The crosswalk's stored decision linking a source record to an LEI, with
    everything needed to check it: score, gap, runner-up, each feature's
    points, and the config that produced it. Reviews are separate records."""

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
    reviews: list[MatchReview] = []
