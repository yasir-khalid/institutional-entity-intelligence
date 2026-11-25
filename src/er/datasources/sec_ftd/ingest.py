"""SEC fails-to-deliver files -> one row per CUSIP per settlement date.

A day's figure is the aggregate balance of fails outstanding in NSCC's CNS
system that day, not the fails that newly occurred, so consecutive days must
not be summed. The price is the prior day's close as SEC reports it, and is
"." when SEC has none.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import FailToDeliver
from .schema import FTD_SCHEMA


def _price(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", ".") else None
    except ValueError:
        return None


def parse_zip(path: Path, writer: BatchedParquetWriter, ingested_at: str) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as raw:
            stream = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            for row in csv.DictReader(stream, delimiter="|"):
                settled = row.get("SETTLEMENT DATE") or ""
                if not settled.isdigit() or not row.get("CUSIP"):
                    continue  # the file ends with "Trailer record count" lines
                day = datetime.strptime(settled, "%Y%m%d").date().isoformat()
                writer.add(FailToDeliver(
                    settlement_date=day,
                    cusip=row["CUSIP"].strip().upper(),
                    symbol=(row.get("SYMBOL") or "").strip().upper() or None,
                    quantity=int(row["QUANTITY (FAILS)"]),
                    description=(row.get("DESCRIPTION") or "").strip() or None,
                    price=_price(row.get("PRICE")),
                    source_file=path.name,
                    snapshot_date=day,
                    ingested_at=ingested_at,
                ).model_dump())
                count += 1
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    source = cfg.sec_ftd
    for url in source.source_urls:
        download_if_missing(url, source.raw_dir / url.rsplit("/", 1)[-1])
    writer = BatchedParquetWriter(source.processed_dir / "sec_ftd.parquet", FTD_SCHEMA, source.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    paths = sorted(source.raw_dir.glob("cnsfails*.zip"))
    rows = sum(parse_zip(path, writer, ingested_at) for path in paths)
    writer.close()
    return {"files": len(paths), "rows": rows}
