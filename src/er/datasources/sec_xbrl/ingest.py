"""Ingest SEC XBRL company facts into Parquet - see er.datasources.sec_xbrl.models.

Owns its parsing end to end (AGENTS.md): the raw companyfacts JSON is fetched
straight from data.sec.gov, filtered to the configured tags, run through the
XbrlFact pydantic boundary, and streamed to Parquet. Nothing here imports
another source's internals; the only cross-source read is the CIK list it
derives from already-processed 13D/G and Forms 3/4/5 tables, which is a build
input (a choice of which issuers to fetch), not shared parsing logic.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import XbrlFact, XbrlIssuer
from .schema import XBRL_FACT_SCHEMA, XBRL_ISSUER_SCHEMA


logger = logging.getLogger(__name__)

# Concepts worth the agent's while; the taxonomy is us-gaap for domestic filers
# and ifrs-full for foreign private issuers.
TAXONOMIES = ("us-gaap", "ifrs-full")


def _cik(value: object) -> str:
    text = str(value or "").strip().lstrip("0") or "0"
    return text.zfill(10)


def _derived_issuer_ciks(cfg: AppConfig, limit: int) -> list[str]:
    """The issuers this dataset already talks about: the CIKs named in Schedule
    13D/G and Forms 3/4/5 records, ranked by how often they appear. Empty when
    neither source has been ingested yet."""
    tables = {
        "sec_insider_relationships": cfg.sec_insiders.processed_dir / "sec_insider_relationships.parquet",
        "sec_13dg_ownership": cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet",
    }
    selects = [
        f"SELECT issuer_cik AS cik FROM read_parquet('{path}') WHERE issuer_cik IS NOT NULL"
        for path in tables.values()
        if path.exists()
    ]
    if not selects:
        return []
    with duckdb.connect() as con:
        rows = con.execute(
            f"SELECT cik, count(*) AS n FROM ({' UNION ALL '.join(selects)}) GROUP BY cik ORDER BY n DESC, cik LIMIT {limit}"
        ).fetchall()
    return [_cik(cik) for cik, _ in rows]


def issuer_ciks(cfg: AppConfig) -> list[str]:
    if cfg.sec_xbrl.ciks:
        return list(dict.fromkeys(_cik(cik) for cik in cfg.sec_xbrl.ciks))
    return _derived_issuer_ciks(cfg, cfg.sec_xbrl.max_issuers)


def parse_company_facts(
    cfg: AppConfig, cik: str, payload: dict, provenance: dict
) -> tuple[list[dict], dict]:
    """Filter one companyfacts payload to the configured tags, producing cleaned
    fact rows plus that issuer's identity row."""
    entity_name = str(payload.get("entityName") or "").strip()
    wanted = set(cfg.sec_xbrl.tags)
    facts: list[dict] = []
    for taxonomy in TAXONOMIES:
        for tag, concept in (payload.get("facts", {}).get(taxonomy) or {}).items():
            if tag not in wanted:
                continue
            label = concept.get("label")
            for unit, entries in (concept.get("units") or {}).items():
                for entry in entries:
                    value = entry.get("val")
                    end = entry.get("end")
                    filed = entry.get("filed")
                    if value is None or not end or not filed:
                        continue
                    try:
                        number = float(value)
                    except (TypeError, ValueError):
                        continue
                    facts.append(
                        XbrlFact(
                            cik=cik,
                            entity_name=entity_name,
                            taxonomy=taxonomy,
                            tag=tag,
                            label=label,
                            unit=unit,
                            value=number,
                            period_start=entry.get("start"),
                            period_end=end,
                            fiscal_year=entry.get("fy"),
                            fiscal_period=entry.get("fp"),
                            form=entry.get("form"),
                            filed=filed,
                            accession_number=entry.get("accn"),
                            frame=entry.get("frame"),
                            **provenance,
                        ).model_dump()
                    )
    issuer = XbrlIssuer(
        cik=cik,
        entity_name=entity_name or cik,
        source_file=provenance.get("source_file"),
        snapshot_date=provenance.get("snapshot_date"),
        ingested_at=provenance.get("ingested_at"),
    ).model_dump()
    return facts, issuer


def _issuer_metadata(cfg: AppConfig, ciks: list[str]) -> dict[str, dict]:
    """Tickers, former names and SIC codes from the EDGAR submissions table, if
    it has been ingested - so the tool can resolve an issuer by ticker or name,
    not only by CIK."""
    path = cfg.sec_submissions.processed_dir / "sec_submissions.parquet"
    if not path.exists() or not ciks:
        return {}
    with duckdb.connect() as con:
        rows = con.execute(
            f"SELECT cik, tickers, former_names, sic, sic_description, fiscal_year_end "
            f"FROM read_parquet('{path}') WHERE cik IN ({','.join(['?'] * len(ciks))})",
            ciks,
        ).fetchall()
    columns = ("tickers", "former_names", "sic", "sic_description", "fiscal_year_end")
    return {_cik(row[0]): dict(zip(columns, row[1:])) for row in rows}


def fetch_company_facts(cfg: AppConfig, cik: str) -> dict | None:
    url = cfg.sec_xbrl.company_facts_url.format(cik=cik)
    path = cfg.sec_xbrl.raw_dir / f"CIK{cik}.json"
    try:
        download_if_missing(url, path, user_agent=cfg.sec_xbrl.user_agent)
    except httpx.HTTPStatusError as exc:
        # A CIK with no XBRL facts answers 404; that is data, not a failure.
        logger.warning("sec_xbrl: CIK %s returned %s; skipping", cik, exc.response.status_code)
        return None
    return json.loads(path.read_text())


def run_all(cfg: AppConfig) -> dict[str, int]:
    ciks = issuer_ciks(cfg)
    facts_path = cfg.sec_xbrl.processed_dir / "sec_xbrl_facts.parquet"
    issuers_path = cfg.sec_xbrl.processed_dir / "sec_xbrl_issuers.parquet"
    writer = BatchedParquetWriter(facts_path, XBRL_FACT_SCHEMA, cfg.sec_xbrl.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    delay = 1.0 / cfg.sec_xbrl.requests_per_second if cfg.sec_xbrl.requests_per_second > 0 else 0.0

    fact_count = 0
    issuers: list[dict] = []
    for index, cik in enumerate(ciks):
        if index:
            time.sleep(delay)
        payload = fetch_company_facts(cfg, cik)
        if payload is None:
            continue
        provenance = {
            "source_file": f"companyfacts/CIK{cik}.json",
            "snapshot_date": snapshot_date,
            "ingested_at": ingested_at,
        }
        rows, issuer = parse_company_facts(cfg, cik, payload, provenance)
        for row in rows:
            writer.add(row)
            fact_count += 1
        issuers.append(issuer)
    writer.close()

    metadata = _issuer_metadata(cfg, [issuer["cik"] for issuer in issuers])
    for issuer in issuers:
        for key, value in metadata.get(issuer["cik"], {}).items():
            issuer[key] = value
    issuer_writer = BatchedParquetWriter(issuers_path, XBRL_ISSUER_SCHEMA, cfg.sec_xbrl.batch_size)
    for issuer in issuers:
        issuer_writer.add(issuer)
    issuer_writer.close()
    return {"issuers": len(issuers), "facts": fact_count}
