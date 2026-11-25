"""FINRA's daily Reg SHO short sale volume files -> one row per symbol per trading day.

This is the volume of trades marked short on FINRA-reported venues that day -
not short interest (the open short position), which FINRA publishes twice a
month. Market-maker hedging puts much of normal volume in this file, so a
"short volume ratio" is a flow statistic, never a measure of how short a
stock is.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import ShortVolume
from .schema import SHORT_VOLUME_SCHEMA


def _weekdays(end: date, days: int) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(days) if (end - timedelta(days=offset)).weekday() < 5]


def download(cfg: AppConfig, end: date | None = None) -> list[Path]:
    source = cfg.finra_short_volume
    paths = []
    for day in _weekdays(end or date.today(), source.lookback_days):
        name = f"CNMSshvol{day:%Y%m%d}.txt"
        try:
            paths.append(download_if_missing(source.base_url + name, source.raw_dir / name))
        except httpx.HTTPStatusError as exc:
            # Market holidays and days not yet published have no file.
            if exc.response.status_code not in (403, 404):
                raise
    return paths


def parse_file(path: Path, writer: BatchedParquetWriter, ingested_at: str) -> int:
    count = 0
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="|"):
            if not row.get("Symbol") or not (row.get("Date") or "").isdigit():
                continue
            day = datetime.strptime(row["Date"], "%Y%m%d").date().isoformat()
            writer.add(ShortVolume(
                trade_date=day,
                symbol=row["Symbol"].strip().upper(),
                short_volume=float(row["ShortVolume"]),
                short_exempt_volume=float(row["ShortExemptVolume"]) if row.get("ShortExemptVolume") else None,
                total_volume=float(row["TotalVolume"]),
                markets=[market for market in (row.get("Market") or "").split(",") if market],
                source_file=path.name,
                snapshot_date=day,
                ingested_at=ingested_at,
            ).model_dump())
            count += 1
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    source = cfg.finra_short_volume
    download(cfg)
    writer = BatchedParquetWriter(source.processed_dir / "finra_short_volume.parquet", SHORT_VOLUME_SCHEMA, source.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    paths = sorted(source.raw_dir.glob("CNMSshvol*.txt"))
    rows = sum(parse_file(path, writer, ingested_at) for path in paths)
    writer.close()
    return {"days": len(paths), "rows": rows}
