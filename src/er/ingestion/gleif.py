"""Streaming parsers: GLEIF concatenated-file XML (inside zip) -> canonical Parquet.

Never loads a full XML tree into memory - the Level 1 entity file alone is ~8.4GB
uncompressed. Uses lxml.etree.iterparse and clears each record element (and its
now-unneeded preceding siblings) as soon as it has been consumed.
"""

from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path

from lxml import etree

from er.config import AppConfig, load_config
from er.ingestion.parquet_writer import (
    ENTITY_SCHEMA,
    EXCEPTION_SCHEMA,
    RELATIONSHIP_SCHEMA,
    BatchedParquetWriter,
)
from er.normalisation.addresses import (
    normalize_city,
    normalize_country,
    normalize_postcode,
    postcode_outward,
)
from er.normalisation.names import build_name_fields, normalize_name

logger = logging.getLogger(__name__)

LEI_NS = "http://www.gleif.org/data/schema/leidata/2016"
RR_NS = "http://www.gleif.org/data/schema/rr/2016"
REPEX_NS = "http://www.gleif.org/data/schema/repex/2016"

LOG_EVERY = 200_000


def _open_zip_member(zip_path: Path):
    zf = zipfile.ZipFile(zip_path)
    (name,) = zf.namelist()
    return zf.open(name)


def _clear_element(elem: etree._Element) -> None:
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]


def _text(elem: etree._Element | None) -> str | None:
    if elem is None:
        return None
    text = elem.text
    return text.strip() if text else None


def _address_fields(entity: etree._Element, tag: str, ns: str) -> dict:
    addr = entity.find(f"{{{ns}}}{tag}")
    if addr is None:
        return {"line1": None, "city": None, "region": None, "postcode": None, "country": None}
    return {
        "line1": _text(addr.find(f"{{{ns}}}FirstAddressLine")),
        "city": _text(addr.find(f"{{{ns}}}City")),
        "region": _text(addr.find(f"{{{ns}}}Region")),
        "postcode": _text(addr.find(f"{{{ns}}}PostalCode")),
        "country": _text(addr.find(f"{{{ns}}}Country")),
    }


def parse_entities(cfg: AppConfig) -> int:
    ns = LEI_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.entities_zip
    out_path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    writer = BatchedParquetWriter(out_path, ENTITY_SCHEMA, cfg.gleif.batch_size)

    started = time.monotonic()
    stream = _open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=f"{{{ns}}}LEIRecord")

    count = 0
    for _, record in context:
        lei = _text(record.find(f"{{{ns}}}LEI"))
        entity = record.find(f"{{{ns}}}Entity")
        registration = record.find(f"{{{ns}}}Registration")

        legal_name = _text(entity.find(f"{{{ns}}}LegalName")) if entity is not None else None
        aliases = []
        if entity is not None:
            other_names = entity.find(f"{{{ns}}}OtherEntityNames")
            if other_names is not None:
                aliases = [
                    t
                    for t in (
                        _text(n) for n in other_names.findall(f"{{{ns}}}OtherEntityName")
                    )
                    if t
                ]

        legal_form = entity.find(f"{{{ns}}}LegalForm") if entity is not None else None
        reg_authority = (
            entity.find(f"{{{ns}}}RegistrationAuthority") if entity is not None else None
        )

        legal_addr = _address_fields(entity, "LegalAddress", ns) if entity is not None else {}
        hq_addr = _address_fields(entity, "HeadquartersAddress", ns) if entity is not None else {}

        name_fields = build_name_fields(legal_name or "")
        legal_postcode_norm = normalize_postcode(legal_addr.get("postcode"))

        row = {
            "lei": lei,
            "legal_name": legal_name,
            "legal_name_norm": name_fields["legal_name_norm"],
            "legal_name_core": name_fields["legal_name_core"],
            "aliases": aliases,
            "aliases_norm": [normalize_name(a) for a in aliases],
            "entity_status": _text(entity.find(f"{{{ns}}}EntityStatus")) if entity is not None else None,
            "entity_category": _text(entity.find(f"{{{ns}}}EntityCategory")) if entity is not None else None,
            "jurisdiction": _text(entity.find(f"{{{ns}}}LegalJurisdiction")) if entity is not None else None,
            "legal_form_code": _text(legal_form.find(f"{{{ns}}}EntityLegalFormCode")) if legal_form is not None else None,
            "registration_authority_id": _text(reg_authority.find(f"{{{ns}}}RegistrationAuthorityID")) if reg_authority is not None else None,
            "registration_id": _text(reg_authority.find(f"{{{ns}}}RegistrationAuthorityEntityID")) if reg_authority is not None else None,
            "registration_status": _text(registration.find(f"{{{ns}}}RegistrationStatus")) if registration is not None else None,
            "legal_address_line1": legal_addr.get("line1"),
            "legal_city": normalize_city(legal_addr.get("city")),
            "legal_region": legal_addr.get("region"),
            "legal_postcode": legal_postcode_norm,
            "legal_country": normalize_country(legal_addr.get("country")),
            "hq_address_line1": hq_addr.get("line1"),
            "hq_city": normalize_city(hq_addr.get("city")),
            "hq_region": hq_addr.get("region"),
            "hq_postcode": normalize_postcode(hq_addr.get("postcode")),
            "hq_country": normalize_country(hq_addr.get("country")),
            "initial_registration_date": _text(registration.find(f"{{{ns}}}InitialRegistrationDate")) if registration is not None else None,
            "last_update_date": _text(registration.find(f"{{{ns}}}LastUpdateDate")) if registration is not None else None,
            "next_renewal_date": _text(registration.find(f"{{{ns}}}NextRenewalDate")) if registration is not None else None,
            "name_tokens": name_fields["name_tokens"],
            "postcode_prefix": postcode_outward(legal_postcode_norm),
            "fund_number": name_fields["fund_number"],
            "is_master": name_fields["is_master"],
            "is_feeder": name_fields["is_feeder"],
            "is_offshore": name_fields["is_offshore"],
            "is_domestic": name_fields["is_domestic"],
        }
        writer.add(row)
        count += 1
        _clear_element(record)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("entities: %d parsed (%.0fs, %.0f/s)", count, elapsed, count / elapsed)

    writer.close()
    stream.close()
    logger.info("entities: done, %d records -> %s", count, out_path)
    return count


def parse_relationships(cfg: AppConfig) -> int:
    ns = RR_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.relationships_zip
    out_path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    writer = BatchedParquetWriter(out_path, RELATIONSHIP_SCHEMA, cfg.gleif.batch_size)

    started = time.monotonic()
    stream = _open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=f"{{{ns}}}RelationshipRecord")

    count = 0
    for _, record in context:
        rel = record.find(f"{{{ns}}}Relationship")
        start_node = rel.find(f"{{{ns}}}StartNode") if rel is not None else None
        end_node = rel.find(f"{{{ns}}}EndNode") if rel is not None else None

        start_date = end_date = None
        if rel is not None:
            periods = rel.find(f"{{{ns}}}RelationshipPeriods")
            if periods is not None:
                chosen = None
                for period in periods.findall(f"{{{ns}}}RelationshipPeriod"):
                    if _text(period.find(f"{{{ns}}}PeriodType")) == "RELATIONSHIP_PERIOD":
                        chosen = period
                        break
                if chosen is None:
                    chosen = periods.find(f"{{{ns}}}RelationshipPeriod")
                if chosen is not None:
                    start_date = _text(chosen.find(f"{{{ns}}}StartDate"))
                    end_date = _text(chosen.find(f"{{{ns}}}EndDate"))

        row = {
            "start_node_id": _text(start_node.find(f"{{{ns}}}NodeID")) if start_node is not None else None,
            "start_node_id_type": _text(start_node.find(f"{{{ns}}}NodeIDType")) if start_node is not None else None,
            "end_node_id": _text(end_node.find(f"{{{ns}}}NodeID")) if end_node is not None else None,
            "end_node_id_type": _text(end_node.find(f"{{{ns}}}NodeIDType")) if end_node is not None else None,
            "relationship_type": _text(rel.find(f"{{{ns}}}RelationshipType")) if rel is not None else None,
            "relationship_status": _text(rel.find(f"{{{ns}}}RelationshipStatus")) if rel is not None else None,
            "start_date": start_date,
            "end_date": end_date,
        }
        writer.add(row)
        count += 1
        _clear_element(record)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("relationships: %d parsed (%.0fs)", count, elapsed)

    writer.close()
    stream.close()
    logger.info("relationships: done, %d records -> %s", count, out_path)
    return count


def parse_exceptions(cfg: AppConfig) -> int:
    ns = REPEX_NS
    zip_path = cfg.gleif.raw_dir / cfg.gleif.exceptions_zip
    out_path = cfg.gleif.processed_dir / "gleif_exceptions.parquet"
    writer = BatchedParquetWriter(out_path, EXCEPTION_SCHEMA, cfg.gleif.batch_size)

    started = time.monotonic()
    stream = _open_zip_member(zip_path)
    context = etree.iterparse(stream, tag=f"{{{ns}}}Exception")

    count = 0
    for _, record in context:
        row = {
            "lei": _text(record.find(f"{{{ns}}}LEI")),
            "exception_category": _text(record.find(f"{{{ns}}}ExceptionCategory")),
            "exception_reason": _text(record.find(f"{{{ns}}}ExceptionReason")),
        }
        writer.add(row)
        count += 1
        _clear_element(record)

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("exceptions: %d parsed (%.0fs)", count, elapsed)

    writer.close()
    stream.close()
    logger.info("exceptions: done, %d records -> %s", count, out_path)
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    n_entities = parse_entities(cfg)
    n_rels = parse_relationships(cfg)
    n_exceptions = parse_exceptions(cfg)
    logger.info(
        "ingestion complete: %d entities, %d relationships, %d exceptions",
        n_entities,
        n_rels,
        n_exceptions,
    )


if __name__ == "__main__":
    main()
