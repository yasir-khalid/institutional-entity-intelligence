"""Streaming parsers: GLEIF concatenated-file XML (inside zip) -> canonical Parquet.

Never loads a full XML tree into memory - the Level 1 entity file alone is ~8.4GB
uncompressed. Uses lxml.etree.iterparse and clears each record element (and its
now-unneeded preceding siblings) as soon as it has been consumed.

Each record goes: raw XML element -> extracted + normalized field groups
(er.datasources.gleif.fields) -> validated through the source's own pydantic
model (er.datasources.gleif.models) -> written to Parquet. That middle step is a
real data-quality gate, not decoration - a malformed record fails loudly here
rather than silently reaching the canonical store.

Entry point: `python -m er.datasources.gleif.ingest` (or `make ingest-gleif`) runs
all four of GLEIF's raw files (entities, relationships, exceptions, ISIN<->LEI) as
one pipeline - see isin_lei.py for the fourth parser, kept in its own file since
it's a plain CSV, not XML.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from lxml import etree

from er.config import AppConfig, load_config
from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.common.xml_utils import clear_element, element_text, open_zip_member
from er.datasources.gleif.fields import (
    extract_addresses,
    extract_legal_form,
    extract_name_fields,
    extract_registration,
    extract_registration_dates,
    extract_status_fields,
)
from er.datasources.gleif.isin_lei import parse_isin_lei
from er.datasources.gleif.models import GleifEntity, GleifRelationship, GleifRelationshipException
from er.datasources.gleif.schema import (
    ENTITY_SCHEMA,
    RELATIONSHIP_EXCEPTION_SCHEMA,
    RELATIONSHIP_SCHEMA,
)

logger = logging.getLogger(__name__)

LEI_NS = "http://www.gleif.org/data/schema/leidata/2016"
RR_NS = "http://www.gleif.org/data/schema/rr/2016"
REPEX_NS = "http://www.gleif.org/data/schema/repex/2016"

LOG_EVERY = 200_000


def _ingested_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_entities_by_lei(path: Path) -> int:
    """GLEIF's concatenated file merges dozens of per-LOU source feeds (visible in its
    own header as separate <gleif:Source> blocks) and occasionally emits the same LEI
    twice with only last_update_date differing - a near-simultaneous-update artifact of
    that merge, not a real second entity. LEI must be a true unique key downstream (the
    ISIN-bridge join, OpenSearch _id), so keep only the most-recently-updated row.
    """
    tmp_path = path.with_suffix(".dedup.parquet")
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY lei ORDER BY last_update_date DESC NULLS LAST
                ) AS rn
                FROM read_parquet('{path}')
            )
            WHERE rn = 1
        ) TO '{tmp_path}' (FORMAT PARQUET)
    """)
    (before,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()
    (after,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{tmp_path}')").fetchone()
    con.close()
    tmp_path.replace(path)
    removed = before - after
    if removed:
        logger.info("entities: removed %d duplicate-LEI rows (kept most recent)", removed)
    return after


def _build_entity_row(record: etree._Element, ns: str, provenance: dict) -> dict:
    """Compose one entity row from the field-group extractors in fields.py, then
    validate it through GleifEntity - the raw -> cleaned model boundary."""
    lei = element_text(record.find(f"{{{ns}}}LEI"))
    entity = record.find(f"{{{ns}}}Entity")
    registration = record.find(f"{{{ns}}}Registration")

    fields = {
        "lei": lei,
        **extract_name_fields(entity, ns),
        **extract_legal_form(entity, ns),
        **extract_registration(entity, ns),
        **extract_addresses(entity, ns),
        **extract_status_fields(entity, ns),
        **extract_registration_dates(registration, ns),
        **provenance,
    }
    return GleifEntity(**fields).model_dump()


def parse_entities(cfg: AppConfig) -> int:
    ns = LEI_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.entities_zip
    out_path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    writer = BatchedParquetWriter(out_path, ENTITY_SCHEMA, cfg.gleif.batch_size)

    ingested_at = _ingested_at()
    source_file = zip_path.name
    snapshot_date: str | None = None

    started = time.monotonic()
    stream = open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=(f"{{{ns}}}ContentDate", f"{{{ns}}}LEIRecord"))

    count = 0
    for _, elem in context:
        if elem.tag == f"{{{ns}}}ContentDate":
            if snapshot_date is None:
                text = element_text(elem)
                snapshot_date = text[:10] if text else None
            clear_element(elem)
            continue

        provenance = {"source_file": source_file, "snapshot_date": snapshot_date, "ingested_at": ingested_at}
        row = _build_entity_row(elem, ns, provenance)
        writer.add(row)
        count += 1
        clear_element(elem)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("entities: %d parsed (%.0fs, %.0f/s)", count, elapsed, count / elapsed)

    writer.close()
    stream.close()
    final_count = _dedupe_entities_by_lei(out_path)
    logger.info("entities: done, %d records parsed, %d after dedup -> %s", count, final_count, out_path)
    return final_count


def _build_relationship_row(record: etree._Element, ns: str, provenance: dict) -> dict:
    rel = record.find(f"{{{ns}}}Relationship")
    start_node = rel.find(f"{{{ns}}}StartNode") if rel is not None else None
    end_node = rel.find(f"{{{ns}}}EndNode") if rel is not None else None

    start_date = end_date = None
    if rel is not None:
        periods = rel.find(f"{{{ns}}}RelationshipPeriods")
        if periods is not None:
            chosen = None
            for period in periods.findall(f"{{{ns}}}RelationshipPeriod"):
                if element_text(period.find(f"{{{ns}}}PeriodType")) == "RELATIONSHIP_PERIOD":
                    chosen = period
                    break
            if chosen is None:
                chosen = periods.find(f"{{{ns}}}RelationshipPeriod")
            if chosen is not None:
                start_date = element_text(chosen.find(f"{{{ns}}}StartDate"))
                end_date = element_text(chosen.find(f"{{{ns}}}EndDate"))

    fields = {
        "start_node_id": element_text(start_node.find(f"{{{ns}}}NodeID")) if start_node is not None else None,
        "start_node_id_type": element_text(start_node.find(f"{{{ns}}}NodeIDType")) if start_node is not None else None,
        "end_node_id": element_text(end_node.find(f"{{{ns}}}NodeID")) if end_node is not None else None,
        "end_node_id_type": element_text(end_node.find(f"{{{ns}}}NodeIDType")) if end_node is not None else None,
        "relationship_type": element_text(rel.find(f"{{{ns}}}RelationshipType")) if rel is not None else None,
        "relationship_status": element_text(rel.find(f"{{{ns}}}RelationshipStatus")) if rel is not None else None,
        "start_date": start_date,
        "end_date": end_date,
        **provenance,
    }
    return GleifRelationship(**fields).model_dump()


def parse_relationships(cfg: AppConfig) -> int:
    ns = RR_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.relationships_zip
    out_path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    writer = BatchedParquetWriter(out_path, RELATIONSHIP_SCHEMA, cfg.gleif.batch_size)

    ingested_at = _ingested_at()
    source_file = zip_path.name
    snapshot_date: str | None = None

    started = time.monotonic()
    stream = open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=(f"{{{ns}}}ContentDate", f"{{{ns}}}RelationshipRecord"))

    count = 0
    for _, elem in context:
        if elem.tag == f"{{{ns}}}ContentDate":
            if snapshot_date is None:
                text = element_text(elem)
                snapshot_date = text[:10] if text else None
            clear_element(elem)
            continue

        provenance = {"source_file": source_file, "snapshot_date": snapshot_date, "ingested_at": ingested_at}
        row = _build_relationship_row(elem, ns, provenance)
        writer.add(row)
        count += 1
        clear_element(elem)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("relationships: %d parsed (%.0fs)", count, elapsed)

    writer.close()
    stream.close()
    logger.info("relationships: done, %d records -> %s", count, out_path)
    return count


def parse_relationship_exceptions(cfg: AppConfig) -> int:
    ns = REPEX_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.exceptions_zip
    out_path = cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet"
    writer = BatchedParquetWriter(out_path, RELATIONSHIP_EXCEPTION_SCHEMA, cfg.gleif.batch_size)

    ingested_at = _ingested_at()
    source_file = zip_path.name
    snapshot_date: str | None = None

    started = time.monotonic()
    stream = open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=(f"{{{ns}}}ContentDate", f"{{{ns}}}Exception"))

    count = 0
    for _, elem in context:
        if elem.tag == f"{{{ns}}}ContentDate":
            if snapshot_date is None:
                text = element_text(elem)
                snapshot_date = text[:10] if text else None
            clear_element(elem)
            continue

        fields = {
            "lei": element_text(elem.find(f"{{{ns}}}LEI")),
            "exception_category": element_text(elem.find(f"{{{ns}}}ExceptionCategory")),
            "exception_reason": element_text(elem.find(f"{{{ns}}}ExceptionReason")),
            "source_file": source_file,
            "snapshot_date": snapshot_date,
            "ingested_at": ingested_at,
        }
        row = GleifRelationshipException(**fields).model_dump()
        writer.add(row)
        count += 1
        clear_element(elem)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("relationship_exceptions: %d parsed (%.0fs)", count, elapsed)

    writer.close()
    stream.close()
    logger.info("relationship_exceptions: done, %d records -> %s", count, out_path)
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    n_entities = parse_entities(cfg)
    n_rels = parse_relationships(cfg)
    n_exceptions = parse_relationship_exceptions(cfg)
    n_isin_lei = parse_isin_lei(cfg)
    logger.info(
        "ingestion complete: %d entities, %d relationships, %d relationship_exceptions, %d isin_lei",
        n_entities,
        n_rels,
        n_exceptions,
        n_isin_lei,
    )


if __name__ == "__main__":
    main()
