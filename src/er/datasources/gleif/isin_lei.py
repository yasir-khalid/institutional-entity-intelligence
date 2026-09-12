"""Streaming parser: ISIN<->LEI mapping CSV (inside zip) -> Parquet.

Plain 2-column CSV (~9.26M rows) - no XML/lxml needed, but still streamed and
flushed in bounded-memory batches like the GLEIF XML parsers.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig, load_config
from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.gleif.schema import ISIN_LEI_SCHEMA

logger = logging.getLogger(__name__)

LOG_EVERY = 1_000_000

_FILENAME_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def _open_zip_member(zip_path: Path):
    zf = zipfile.ZipFile(zip_path)
    (name,) = zf.namelist()
    return zf.open(name)


def _snapshot_date_from_filename(filename: str) -> str | None:
    match = _FILENAME_DATE_RE.search(filename)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def parse_isin_lei(cfg: AppConfig) -> int:
    zip_path = cfg.gleif.raw_dir / cfg.gleif.isin_lei_zip
    out_path = cfg.gleif.processed_dir / "isin_lei.parquet"
    writer = BatchedParquetWriter(out_path, ISIN_LEI_SCHEMA, cfg.gleif.batch_size)

    source_file = zip_path.name
    snapshot_date = _snapshot_date_from_filename(source_file)
    ingested_at = datetime.now(timezone.utc).isoformat()

    started = time.monotonic()
    stream = io.TextIOWrapper(_open_zip_member(zip_path), encoding="utf-8", newline="")
    reader = csv.reader(stream)
    header = next(reader)
    assert [h.strip().upper() for h in header] == ["LEI", "ISIN"], f"unexpected header: {header}"

    count = 0
    for lei, isin in reader:
        row = {
            "isin": isin.strip(),
            "lei": lei.strip(),
            "source_file": source_file,
            "snapshot_date": snapshot_date,
            "ingested_at": ingested_at,
        }
        writer.add(row)
        count += 1

        if count % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("isin_lei: %d parsed (%.0fs, %.0f/s)", count, elapsed, count / elapsed)

    writer.close()
    stream.close()
    logger.info("isin_lei: done, %d records -> %s", count, out_path)
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    parse_isin_lei(cfg)


if __name__ == "__main__":
    main()
