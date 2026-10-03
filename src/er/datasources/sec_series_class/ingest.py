from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import SecSeriesClass
from .schema import SERIES_CLASS_SCHEMA


_YEAR_RE = re.compile(r"(20\d{2})")


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def parse_file(cfg: AppConfig, path: Path) -> int:
    out_path = cfg.sec_series_class.processed_dir / "sec_series_classes.parquet"
    writer = BatchedParquetWriter(out_path, SERIES_CLASS_SCHEMA, cfg.sec_series_class.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    match = _YEAR_RE.search(path.name)
    snapshot_date = f"{match.group(1)}-12-31" if match else None

    count = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            row = SecSeriesClass(
                reporting_file_number=(raw.get("Reporting File Number") or "").strip(),
                cik=(raw.get("CIK Number") or "").strip(),
                entity_name=(raw.get("Entity Name") or "").strip(),
                entity_org_type=_clean(raw.get("Entity Org Type")),
                series_id=(raw.get("Series ID") or "").strip(),
                series_name=(raw.get("Series Name") or "").strip(),
                class_id=_clean(raw.get("Class ID")),
                class_name=_clean(raw.get("Class Name")),
                class_ticker=_clean(raw.get("Class Ticker")),
                address_1=_clean(raw.get("Address_1")),
                address_2=_clean(raw.get("Address_2")),
                city=_clean(raw.get("City")),
                state=_clean(raw.get("State")),
                zip_code=_clean(raw.get("Zip Code")),
                source_file=path.name,
                snapshot_date=snapshot_date,
                ingested_at=ingested_at,
            )
            writer.add(row.model_dump())
            count += 1
    writer.close()
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    path = download_if_missing(
        cfg.sec_series_class.source_url,
        cfg.sec_series_class.raw_dir / cfg.sec_series_class.source_file,
    )
    return {"series_classes": parse_file(cfg, path)}
