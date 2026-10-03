from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import OpenFigiMapping
from .schema import MAPPING_SCHEMA


def _cusips(cfg: AppConfig) -> list[str]:
    path = cfg.sec_13f.processed_dir / "sec_13f_holdings.parquet"
    if not path.exists():
        raise FileNotFoundError(f"run the SEC 13F ingest first: {path} is missing")
    con = duckdb.connect()
    rows = con.sql(
        f"""SELECT DISTINCT upper(trim(cusip)) FROM read_parquet('{path}')
            WHERE cusip IS NOT NULL AND length(trim(cusip)) = 9 ORDER BY 1"""
    ).fetchall()
    con.close()
    return [row[0] for row in rows]


def _cache_path(raw_dir: Path, cusips: list[str]) -> Path:
    digest = hashlib.sha256("\n".join(cusips).encode()).hexdigest()[:16]
    return raw_dir / f"mapping-{digest}.json"


def fetch_missing(cfg: AppConfig, cusips: list[str]) -> int:
    raw_dir = cfg.openfigi.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    api_key = cfg.openfigi_api_key
    batch_size = cfg.openfigi.batch_size_with_key if api_key else cfg.openfigi.batch_size_without_key
    delay = 6 / 25 if api_key else 60 / 25
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    fetched = 0
    with httpx.Client(timeout=60) as client:
        for offset in range(0, len(cusips), batch_size):
            batch = cusips[offset : offset + batch_size]
            cache_path = _cache_path(raw_dir, batch)
            if cache_path.exists():
                continue
            if fetched:
                time.sleep(delay)
            jobs = [{"idType": "ID_CUSIP", "idValue": cusip} for cusip in batch]
            response = client.post(cfg.openfigi.api_url, headers=headers, json=jobs)
            response.raise_for_status()
            payload = {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "jobs": jobs,
                "responses": response.json(),
            }
            cache_path.write_text(json.dumps(payload, separators=(",", ":")))
            fetched += len(batch)
    return fetched


def build_mappings(cfg: AppConfig) -> int:
    out_path = cfg.openfigi.processed_dir / "openfigi_mappings.parquet"
    writer = BatchedParquetWriter(out_path, MAPPING_SCHEMA, 25_000)
    count = 0
    ingested_at = datetime.now(timezone.utc).isoformat()

    latest: dict[str, tuple[str, Path, dict]] = {}
    for path in sorted(cfg.openfigi.raw_dir.glob("mapping-*.json")):
        payload = json.loads(path.read_text())
        for job, response in zip(payload["jobs"], payload["responses"], strict=True):
            requested_at = str(payload["requested_at"])
            current = latest.get(job["idValue"])
            if current is None or requested_at > current[0]:
                latest[job["idValue"]] = (requested_at, path, response)

    for cusip, (requested_at, path, response) in sorted(latest.items()):
        candidates = response.get("data") or [None]
        for rank, candidate in enumerate(candidates, start=1):
            candidate = candidate or {}
            row = OpenFigiMapping(
                cusip=cusip,
                mapping_rank=rank,
                figi=candidate.get("figi"),
                name=candidate.get("name"),
                ticker=candidate.get("ticker"),
                exchange_code=candidate.get("exchCode"),
                market_sector=candidate.get("marketSector"),
                security_type=candidate.get("securityType"),
                security_type_2=candidate.get("securityType2"),
                share_class_figi=candidate.get("shareClassFIGI"),
                composite_figi=candidate.get("compositeFIGI"),
                error=response.get("error") or response.get("warning"),
                source_file=path.name,
                snapshot_date=requested_at[:10],
                ingested_at=ingested_at,
            )
            writer.add(row.model_dump())
            count += 1
    writer.close()
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    cusips = _cusips(cfg)
    fetched = fetch_missing(cfg, cusips)
    return {"requested": fetched, "mappings": build_mappings(cfg)}
