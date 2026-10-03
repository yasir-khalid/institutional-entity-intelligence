from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import NicInstitution, NicRelationship, NicTransformation
from .schema import INSTITUTION_SCHEMA, RELATIONSHIP_SCHEMA, TRANSFORMATION_SCHEMA


# NIC writes 9999-12-31 for "still in force" and 0 where an identifier is absent.
OPEN_ENDED = "99991231"


def _rows(path: Path) -> Iterator[tuple[str, dict[str, str]]]:
    """Yields (snapshot_date, row) with headers normalised - the CSV exports
    prefix the first column with '#' (e.g. #ID_RSSD)."""
    with zipfile.ZipFile(path) as archive:
        (member,) = [info for info in archive.infolist() if info.filename.lower().endswith(".csv")]
        snapshot = date(*member.date_time[:3]).isoformat()
        with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="latin-1", newline="") as stream:
            reader = csv.reader(stream)
            header = [name.strip().lstrip("#").upper() for name in next(reader)]
            for values in reader:
                yield snapshot, dict(zip(header, (value.strip() for value in values)))


def _date(value: str | None) -> str | None:
    if not value or value in ("0", OPEN_ENDED):
        return None
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def _id(value: str | None) -> str | None:
    return value if value and value.strip("0") else None


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _write(cfg: AppConfig, path: Path, name: str, schema, build) -> int:
    writer = BatchedParquetWriter(cfg.ffiec_nic.processed_dir / name, schema, cfg.ffiec_nic.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    count = 0
    for snapshot, raw in _rows(path):
        row = build(raw)
        if row is None:
            continue
        writer.add(
            {**row.model_dump(), "source_file": path.name, "snapshot_date": snapshot, "ingested_at": ingested_at}
        )
        count += 1
    writer.close()
    return count


def _institution(raw: dict[str, str]) -> NicInstitution | None:
    if not _id(raw.get("ID_RSSD")) or not raw.get("NM_LGL"):
        return None
    lei = (raw.get("ID_LEI") or "").upper()
    return NicInstitution(
        rssd_id=raw["ID_RSSD"],
        legal_name=raw["NM_LGL"],
        short_name=raw.get("NM_SHORT") or None,
        entity_type=raw.get("ENTITY_TYPE") or None,
        lei=lei if len(lei) == 20 else None,
        city=raw.get("CITY") or None,
        state=raw.get("STATE_ABBR_NM") or None,
        country=raw.get("CNTRY_NM") or None,
        opened_on=_date(raw.get("DT_OPEN")),
        closed_on=_date(raw.get("DT_END")),
    )


def _relationship(raw: dict[str, str]) -> NicRelationship | None:
    parent, offspring = _id(raw.get("ID_RSSD_PARENT")), _id(raw.get("ID_RSSD_OFFSPRING"))
    if not parent or not offspring:
        return None
    return NicRelationship(
        parent_rssd_id=parent,
        offspring_rssd_id=offspring,
        controlled=raw.get("CTRL_IND") == "1",
        regulatory_level=raw.get("RELN_LVL") or None,
        equity_percent=_number(raw.get("PCT_EQUITY")),
        start_date=_date(raw.get("DT_START")),
        end_date=_date(raw.get("DT_END")),
    )


def _transformation(raw: dict[str, str]) -> NicTransformation | None:
    predecessor, successor = _id(raw.get("ID_RSSD_PREDECESSOR")), _id(raw.get("ID_RSSD_SUCCESSOR"))
    if not predecessor or not successor:
        return None
    return NicTransformation(
        predecessor_rssd_id=predecessor,
        successor_rssd_id=successor,
        transformation_code=raw.get("TRNSFM_CD") or None,
        transformation_date=_date(raw.get("DT_TRANS")),
    )


def _find(raw_dir: Path, keyword: str) -> list[Path]:
    return sorted(path for path in raw_dir.glob("*.zip") if keyword in path.name.upper())


def run_all(cfg: AppConfig) -> dict[str, int]:
    """Parses the NIC bulk CSV zips downloaded by hand from
    https://www.ffiec.gov/npw/FinancialReport/DataDownload (the site refuses
    scripted downloads): CSV_ATTRIBUTES_ACTIVE.zip, CSV_RELATIONSHIPS.zip and
    CSV_TRANSFORMATIONS.zip in data/raw/ffiec_nic."""
    raw_dir = cfg.ffiec_nic.raw_dir
    attributes = _find(raw_dir, "ATTRIBUTES_ACTIVE")
    relationships = _find(raw_dir, "RELATIONSHIPS")
    transformations = _find(raw_dir, "TRANSFORMATIONS")
    if not attributes or not relationships:
        raise FileNotFoundError(f"download the NIC attribute and relationship CSV zips into {raw_dir}")

    counts = {
        "institutions": _write(cfg, attributes[-1], "ffiec_nic_institutions.parquet", INSTITUTION_SCHEMA, _institution),
        "relationships": _write(
            cfg, relationships[-1], "ffiec_nic_relationships.parquet", RELATIONSHIP_SCHEMA, _relationship
        ),
        "transformations": 0,
    }
    if transformations:
        counts["transformations"] = _write(
            cfg, transformations[-1], "ffiec_nic_transformations.parquet", TRANSFORMATION_SCHEMA, _transformation
        )
    return counts
