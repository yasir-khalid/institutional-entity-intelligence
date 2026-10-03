from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import NPortFund, NPortHolding
from .schema import FUND_SCHEMA, HOLDING_SCHEMA


TABLES = (
    "SUBMISSION.tsv",
    "REGISTRANT.tsv",
    "FUND_REPORTED_INFO.tsv",
    "FUND_REPORTED_HOLDING.tsv",
    "IDENTIFIERS.tsv",
)


def _read(path: Path) -> str:
    return f"read_csv('{path}', delim='\\t', header=true, quote='', all_varchar=true)"


def _write_funds(cfg: AppConfig, paths: dict[str, Path], provenance: dict) -> int:
    out = cfg.nport.processed_dir / "nport_funds.parquet"
    writer = BatchedParquetWriter(out, FUND_SCHEMA, cfg.nport.batch_size)
    query = f"""
        SELECT s.ACCESSION_NUMBER accession_number, s.FILING_DATE filing_date,
               s.REPORT_DATE report_date, r.CIK cik, r.REGISTRANT_NAME registrant_name,
               r.LEI registrant_lei, f.SERIES_ID series_id, f.SERIES_NAME series_name,
               f.SERIES_LEI series_lei, try_cast(f.TOTAL_ASSETS AS DOUBLE) total_assets,
               try_cast(f.TOTAL_LIABILITIES AS DOUBLE) total_liabilities,
               try_cast(f.NET_ASSETS AS DOUBLE) net_assets
        FROM {_read(paths['SUBMISSION.tsv'])} s
        LEFT JOIN {_read(paths['REGISTRANT.tsv'])} r USING (ACCESSION_NUMBER)
        LEFT JOIN {_read(paths['FUND_REPORTED_INFO.tsv'])} f USING (ACCESSION_NUMBER)
    """
    con = duckdb.connect()
    count = 0
    for batch in con.sql(query).to_arrow_reader(cfg.nport.batch_size):
        for raw in batch.to_pylist():
            writer.add(NPortFund(**raw, **provenance).model_dump())
            count += 1
    writer.close()
    con.close()
    return count


def _write_holdings(cfg: AppConfig, paths: dict[str, Path], provenance: dict) -> int:
    out = cfg.nport.processed_dir / "nport_holdings.parquet"
    writer = BatchedParquetWriter(out, HOLDING_SCHEMA, cfg.nport.batch_size)
    query = f"""
        SELECT h.ACCESSION_NUMBER accession_number, h.HOLDING_ID holding_id,
               h.ISSUER_NAME issuer_name, h.ISSUER_LEI issuer_lei,
               h.ISSUER_TITLE issuer_title, h.ISSUER_CUSIP issuer_cusip,
               max(i.IDENTIFIER_ISIN) isin, max(i.IDENTIFIER_TICKER) ticker,
               try_cast(h.BALANCE AS DOUBLE) balance, h.UNIT unit,
               h.CURRENCY_CODE currency_code, try_cast(h.CURRENCY_VALUE AS DOUBLE) currency_value,
               try_cast(h.EXCHANGE_RATE AS DOUBLE) exchange_rate,
               try_cast(h.PERCENTAGE AS DOUBLE) percentage, h.PAYOFF_PROFILE payoff_profile,
               h.ASSET_CAT asset_category, h.ISSUER_TYPE issuer_type,
               h.INVESTMENT_COUNTRY investment_country, h.FAIR_VALUE_LEVEL fair_value_level,
               h.DERIVATIVE_CAT derivative_category
        FROM {_read(paths['FUND_REPORTED_HOLDING.tsv'])} h
        LEFT JOIN {_read(paths['IDENTIFIERS.tsv'])} i USING (HOLDING_ID)
        GROUP BY ALL
    """
    con = duckdb.connect()
    count = 0
    for batch in con.sql(query).to_arrow_reader(cfg.nport.batch_size):
        for raw in batch.to_pylist():
            writer.add(NPortHolding(**raw, **provenance).model_dump())
            count += 1
    writer.close()
    con.close()
    return count


def _write_observed_links(cfg: AppConfig) -> int:
    holdings = cfg.nport.processed_dir / "nport_holdings.parquet"
    out = cfg.nport.processed_dir / "nport_observed_security_issuers.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT DISTINCT issuer_cusip AS cusip, isin, issuer_lei,
                   issuer_name, source_file, snapshot_date, ingested_at
            FROM read_parquet('{holdings}')
            WHERE regexp_full_match(coalesce(issuer_lei, ''), '[A-Z0-9]{{20}}')
              AND (regexp_full_match(coalesce(issuer_cusip, ''), '[A-Z0-9]{{9}}')
                   OR regexp_full_match(coalesce(isin, ''), '[A-Z0-9]{{12}}'))
        ) TO '{out}' (FORMAT PARQUET)
    """)
    (count,) = con.sql(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()
    con.close()
    return count


def parse_zip(cfg: AppConfig, path: Path) -> dict[str, int]:
    ingested_at = datetime.now(timezone.utc).isoformat()
    snapshot_date = path.stem.split("_")[0]
    provenance = {
        "source_file": path.name,
        "snapshot_date": snapshot_date,
        "ingested_at": ingested_at,
    }
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as archive:
            names = {Path(name).name: name for name in archive.namelist()}
            missing = [name for name in TABLES if name not in names]
            if missing:
                raise ValueError(f"N-PORT archive is missing: {', '.join(missing)}")
            paths = {
                name: Path(archive.extract(names[name], path=tmp))
                for name in TABLES
            }
        funds = _write_funds(cfg, paths, provenance)
        holdings = _write_holdings(cfg, paths, provenance)
    return {
        "funds": funds,
        "holdings": holdings,
        "observed_security_issuers": _write_observed_links(cfg),
    }


def run_all(cfg: AppConfig) -> dict[str, int]:
    matches = sorted(cfg.nport.raw_dir.glob("*nport.zip"))
    if not matches:
        raise FileNotFoundError(f"no *nport.zip found under {cfg.nport.raw_dir}")
    return parse_zip(cfg, matches[-1])
