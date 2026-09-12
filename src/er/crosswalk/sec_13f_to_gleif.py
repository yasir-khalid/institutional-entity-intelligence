"""Crosswalk: resolve each unique SEC Form 13F filer to a GLEIF LEI.

Reuses er.matching.matcher.match() unchanged - a 13F filer name is exactly the same
"which single legal entity is this?" question that function already answers for any
other source, so there is no separate matching logic here. This module's only job is
to adapt 13F's fields into match()'s inputs and persist the results as a crosswalk
table (one row per unique filer, not per filing - a filer appears in many quarterly
filings under the same CIK/name).

Output: data/processed/crosswalk_sec_13f_gleif.parquet - filer_name, cik, crd_number,
resolved lei/decision/score, so any downstream query can join 13F holdings straight
through to GLEIF-anchored entity data.

CLI entry point: `python -m er.cli.crosswalk_sec_13f` (or `make crosswalk-sec-13f`).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa

from er.config import AppConfig
from er.datasources.common.parquet_writer import PROVENANCE_FIELDS, BatchedParquetWriter
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match

logger = logging.getLogger(__name__)

LOG_EVERY = 500

# SEC 13F's FILINGMANAGER_STATEORCOUNTRY field overloads one column with both US state
# codes (domestic filers) and country names (foreign filers) - e.g. "CA", "NY" vs.
# "ENGLAND", "CANADA". GLEIF's legal_country is always a country, so a US state code
# must map to "US" rather than being passed through as-is (which normalize_country_code
# would otherwise leave unrecognized and therefore silently ignore).
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}

CROSSWALK_SCHEMA = pa.schema(
    [
        ("filer_name", pa.string()),
        ("cik", pa.string()),
        ("crd_number", pa.string()),
        ("filer_city", pa.string()),
        ("filer_state_or_country", pa.string()),
        ("resolved_country", pa.string()),
        ("lei", pa.string()),
        ("decision", pa.string()),
        ("score", pa.float64()),
        ("gap", pa.float64()),
        ("reason", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)


def _resolve_country(state_or_country: str | None) -> str | None:
    if not state_or_country:
        return None
    cleaned = state_or_country.strip().upper()
    if cleaned in US_STATE_CODES:
        return "US"
    return cleaned


def _unique_filers(cfg: AppConfig) -> list[dict]:
    """One row per (cik, filer_name) - a filer's name/address is effectively static
    across its quarterly filings, so re-matching per-filing would just repeat the same
    OpenSearch/scoring work thousands of times over for no new information."""
    con = duckdb.connect()
    rows = con.sql(f"""
        SELECT DISTINCT ON (cik)
            cik, filer_name, crd_number, filer_city, filer_state_or_country
        FROM read_parquet('{cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"}')
        WHERE filer_name IS NOT NULL AND filer_name != ''
        ORDER BY cik, filing_date DESC
    """).fetchall()
    con.close()
    return [
        {
            "cik": r[0],
            "filer_name": r[1],
            "crd_number": r[2],
            "filer_city": r[3],
            "filer_state_or_country": r[4],
        }
        for r in rows
    ]


def build_crosswalk(cfg: AppConfig, out_path: Path | None = None) -> int:
    out_path = out_path or (cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet")
    writer = BatchedParquetWriter(out_path, CROSSWALK_SCHEMA, cfg.sec_13f.batch_size)
    client = get_client(cfg)

    filers = _unique_filers(cfg)
    ingested_at = datetime.now(timezone.utc).isoformat()
    snapshot_date = datetime.now(timezone.utc).date().isoformat()

    started = time.monotonic()
    for i, filer in enumerate(filers, start=1):
        country = _resolve_country(filer["filer_state_or_country"])
        result = match(
            client,
            cfg,
            name=filer["filer_name"],
            country=country,
            city=filer["filer_city"],
        )
        writer.add(
            {
                "filer_name": filer["filer_name"],
                "cik": filer["cik"],
                "crd_number": filer["crd_number"],
                "filer_city": filer["filer_city"],
                "filer_state_or_country": filer["filer_state_or_country"],
                "resolved_country": country,
                "lei": result.lei,
                "decision": result.decision.value,
                "score": result.score,
                "gap": result.gap,
                "reason": result.reason,
                "source_file": "sec_13f_filings.parquet",
                "snapshot_date": snapshot_date,
                "ingested_at": ingested_at,
            }
        )
        if i % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("crosswalk: %d/%d filers resolved (%.0fs, %.1f/s)", i, len(filers), elapsed, i / elapsed)

    writer.close()
    logger.info("crosswalk: done, %d filers -> %s", len(filers), out_path)
    return len(filers)


