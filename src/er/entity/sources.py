"""Registry of identifier sources that feed the canonical entity layer.

This is the ONE file to touch when adding a new source's identifiers to the
canonical entity model (a SEC Form ADV CRD number, an FCA FRN, a Companies
House number, ...). Each source contributes a SQL SELECT - not a Python loop
over rows - reading whatever crosswalk/processed table that source already
produces, aliased to exactly these eight columns:

    entity_id (the GLEIF LEI), identifier_type, identifier_value, confidence,
    source, source_file, snapshot_date, ingested_at

The last three are provenance, not decoration: every source's own ingest.py
already stamps them on every row it writes (er.datasources.common.parquet_writer.
PROVENANCE_FIELDS), so carrying them through here costs nothing and answers
"where did this identifier come from, and as of when" for any consumer - a
question that used to be unanswerable once data reached the entity layer,
even though the underlying source tables had it all along.

`er.entity.build` UNIONs every registered source's query with DuckDB and writes
the result in one COPY, so adding a millions-of-rows source never means loading
it into Python. A source function returns None (rather than raising) when its
upstream data hasn't been produced yet - e.g. a fresh checkout that hasn't run
`make crosswalk-sec-13f` - so the entity layer degrades gracefully instead of
failing outright.

To add a new source:
    1. Write one function here: `def my_source_identifiers_sql(cfg) -> str | None`.
    2. Read your source's own processed/crosswalk parquet table (never another
       source's raw files - see AGENTS.md's "each source owns its ETL" rule).
    3. Alias your columns to the eight names above - source_file/snapshot_date/
       ingested_at should already exist on your table if it was written via
       BatchedParquetWriter with PROVENANCE_FIELDS in its schema.
    4. Append the function to IDENTIFIER_SOURCES below.
Nothing else in er.entity needs to change.
"""

from __future__ import annotations

from er.config import AppConfig


def isin_identifiers_sql(cfg: AppConfig) -> str | None:
    """GLEIF's own ISIN<->LEI bridge (ingested since Phase 2, previously used only
    internally by the benchmark's positive-label generation) - a real, useful
    identifier with no matching/crosswalk step needed, since GLEIF publishes the
    mapping directly."""
    path = cfg.gleif.processed_dir / "isin_lei.parquet"
    if not path.exists():
        return None
    return f"""
        SELECT
            lei AS entity_id,
            'ISIN' AS identifier_type,
            isin AS identifier_value,
            'SOURCE' AS confidence,
            'gleif_isin_bridge' AS source,
            source_file,
            snapshot_date,
            ingested_at
        FROM read_parquet('{path}')
    """


def sec_13f_identifiers_sql(cfg: AppConfig) -> str | None:
    """Every SEC 13F filer resolved to a GLEIF LEI via the crosswalk
    (er.crosswalk.sec_13f_to_gleif) contributes its CIK as an identifier.
    UNMATCHED filers contribute nothing - an entity_identifiers row must always
    trace back to a real matching decision, never a guess."""
    path = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    if not path.exists():
        return None
    return f"""
        SELECT
            lei AS entity_id,
            'CIK' AS identifier_type,
            cik AS identifier_value,
            decision AS confidence,
            'sec_13f' AS source,
            source_file,
            snapshot_date,
            ingested_at
        FROM read_parquet('{path}')
        WHERE lei IS NOT NULL AND decision IN ('AUTO_MATCH', 'REVIEW')
    """


# Every source contributing identifiers to the canonical entity layer, in the
# order their queries are unioned. Add a new source by writing one function
# above and appending it here.
IDENTIFIER_SOURCES = [
    isin_identifiers_sql,
    sec_13f_identifiers_sql,
]
