"""Builds the canonical entity layer.

Two output tables:
    entities.parquet             - one row per canonical entity
    entity_identifiers.parquet   - every identifier any registered source has
                                    attached to an entity (see er.entity.sources)

GLEIF is the seed/primary source: every canonical entity starts as one GLEIF
LEI record, since every other source currently onboarded (SEC 13F) reaches
GLEIF entities via a crosswalk rather than introducing genuinely new entities.
`entity_id` is deliberately a distinct column from the GLEIF-specific `lei`
field (even though they're equal today) so a future source that introduces
entities GLEIF doesn't know about has somewhere to attach without a schema
change - `build_entities()`'s seed query is the one place to extend when that
happens.

No pydantic raw->cleaned validation boundary here, unlike a source's own
ingest.py: this layer is built entirely from already-validated processed/
crosswalk tables (each of which enforced its own raw->cleaned boundary already),
not from raw external data - there's nothing new to validate, only to join.

CLI entry point: `python -m er.cli.build_entities` (or `make build-entities`).
"""

from __future__ import annotations

import logging

import duckdb

from er.config import AppConfig
from er.entity.sources import IDENTIFIER_SOURCES

logger = logging.getLogger(__name__)


def build_entities(cfg: AppConfig) -> int:
    out_path = cfg.entity.processed_dir / "entities.parquet"
    entities_path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT
                lei AS entity_id,
                lei AS primary_lei,
                legal_name AS canonical_name,
                entity_category AS entity_type,
                jurisdiction,
                legal_country,
                entity_status,
                -- Lineage: GLEIF's own identity timeline for this entity, carried
                -- through from gleif_entities.parquet (previously dropped here -
                -- ingested since Phase 2 but never reached the canonical layer or
                -- any CLI/API consumer). registration_status distinguishes e.g. an
                -- ISSUED record from one still PENDING_VALIDATION.
                entity_creation_date,
                initial_registration_date,
                last_update_date,
                next_renewal_date,
                registration_status,
                snapshot_date AS gleif_snapshot_date
            FROM read_parquet('{entities_path}')
        ) TO '{out_path}' (FORMAT PARQUET)
    """)
    (n,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()
    con.close()
    logger.info("entities: %d canonical entities (seeded 1:1 from GLEIF) -> %s", n, out_path)
    return n


def build_identifiers(cfg: AppConfig) -> int:
    out_path = cfg.entity.processed_dir / "entity_identifiers.parquet"
    queries = [sql for source in IDENTIFIER_SOURCES if (sql := source(cfg)) is not None]
    if not queries:
        logger.warning("entity_identifiers: no identifier sources have produced data yet - nothing to write")
        return 0

    union_sql = "\nUNION ALL\n".join(queries)
    con = duckdb.connect()
    con.execute(f"COPY ({union_sql}) TO '{out_path}' (FORMAT PARQUET)")
    (n,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()
    con.close()
    logger.info(
        "entity_identifiers: %d identifier rows from %d source(s) -> %s", n, len(queries), out_path
    )
    return n


def run_all(cfg: AppConfig) -> dict[str, int]:
    """Runs the full canonical-entity-layer build. Pure orchestration, no
    logging setup/CLI concerns - see er.cli.build_entities for the
    command-line entry point that calls this and times it."""
    return {
        "entities": build_entities(cfg),
        "identifiers": build_identifiers(cfg),
    }
