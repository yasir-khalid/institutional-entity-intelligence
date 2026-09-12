"""SEC Form 13F bulk data -> canonical Parquet.

Unlike GLEIF's multi-GB XML, 13F's bulk files are modest-size tab-separated files
inside a zip (a few hundred MB uncompressed for INFOTABLE.tsv, the largest one) -
DuckDB can read a TSV member straight out of a zip via read_csv(), so there's no
need for the streaming-iterparse machinery GLEIF requires. Each row still goes
through the source's own pydantic model (er.datasources.sec_13f.models) as the
raw -> cleaned validation boundary, same as every other source.

Two output tables:
  - sec_13f_filings.parquet  (SUBMISSION + COVERPAGE joined on ACCESSION_NUMBER)
  - sec_13f_holdings.parquet (INFOTABLE, one row per reported security position)

CLI entry point: `python -m er.cli.ingest_sec_13f` (or `make ingest-sec-13f`).
"""

from __future__ import annotations

import logging
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.sec_13f.models import Sec13FFiling, Sec13FHolding
from er.datasources.sec_13f.schema import FILING_SCHEMA, HOLDING_SCHEMA
from er.normalisation.names import build_name_fields

logger = logging.getLogger(__name__)

LOG_EVERY = 200_000


def _ingested_at() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _extracted_member(zip_path: Path, member: str):
    """DuckDB's read_csv needs a real file path - it has no zip filesystem support -
    so extract the one TSV member we need into a scratch temp dir rather than
    loading it into memory. Cleaned up on exit regardless of size."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_path) as zf:
            extracted = Path(zf.extract(member, path=tmp_dir))
        yield extracted


def _snapshot_date(zip_path: Path) -> str:
    """The bulk file's own name encodes its reporting window (e.g.
    "01mar2026-31may2026_form13f.zip") - use the window start as the snapshot date,
    same role snapshot_date plays for GLEIF (when this data was as-of)."""
    with _extracted_member(zip_path, "SUBMISSION.tsv") as submission_path:
        con = duckdb.connect()
        (min_date,) = con.sql(
            f"SELECT MIN(strptime(FILING_DATE, '%d-%b-%Y')) FROM read_csv("
            f"'{submission_path}', delim='\t', header=true, quote='', all_varchar=true)"
        ).fetchone()
        con.close()
    return str(min_date)[:10] if min_date else zip_path.stem


def _row_bool(value: str | None) -> bool:
    return (value or "").strip().upper() == "Y"


def parse_filings(cfg: AppConfig, zip_path: Path) -> int:
    out_path = cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"
    writer = BatchedParquetWriter(out_path, FILING_SCHEMA, cfg.sec_13f.batch_size)

    ingested_at = _ingested_at()
    source_file = zip_path.name
    snapshot_date = _snapshot_date(zip_path)

    con = duckdb.connect()
    extract_stack = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(zip_path) as zf:
        submission = zf.extract("SUBMISSION.tsv", path=extract_stack.name)
        coverpage = zf.extract("COVERPAGE.tsv", path=extract_stack.name)
    query = f"""
        SELECT
            s.ACCESSION_NUMBER AS accession_number,
            s.FILING_DATE AS filing_date,
            s.SUBMISSIONTYPE AS submission_type,
            s.CIK AS cik,
            s.PERIODOFREPORT AS period_of_report,
            c.ISAMENDMENT AS is_amendment,
            c.AMENDMENTNO AS amendment_no,
            c.AMENDMENTTYPE AS amendment_type,
            c.FILINGMANAGER_NAME AS filer_name,
            c.FILINGMANAGER_STREET1 AS filer_street1,
            c.FILINGMANAGER_STREET2 AS filer_street2,
            c.FILINGMANAGER_CITY AS filer_city,
            c.FILINGMANAGER_STATEORCOUNTRY AS filer_state_or_country,
            c.FILINGMANAGER_ZIPCODE AS filer_zipcode,
            c.REPORTTYPE AS report_type,
            c.FORM13FFILENUMBER AS form13f_file_number,
            c.CRDNUMBER AS crd_number,
            c.SECFILENUMBER AS sec_file_number,
        FROM read_csv('{submission}', delim='\t', header=true, quote='', all_varchar=true) s
        LEFT JOIN read_csv('{coverpage}', delim='\t', header=true, quote='', all_varchar=true) c
            USING (ACCESSION_NUMBER)
    """
    started = time.monotonic()
    count = 0
    for batch in con.sql(query).to_arrow_reader(cfg.sec_13f.batch_size):
        for record in batch.to_pylist():
            filer_name = record.get("filer_name") or ""
            name_fields = build_name_fields(filer_name)
            fields = {
                **record,
                "is_amendment": _row_bool(record.get("is_amendment")),
                "filer_name": filer_name,
                "filer_name_norm": name_fields["legal_name_norm"],
                "filer_name_core": name_fields["legal_name_core"],
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "ingested_at": ingested_at,
            }
            writer.add(Sec13FFiling(**fields).model_dump())
            count += 1
            if count % LOG_EVERY == 0:
                elapsed = time.monotonic() - started
                logger.info("filings: %d parsed (%.0fs)", count, elapsed)

    writer.close()
    con.close()
    extract_stack.cleanup()
    logger.info("filings: done, %d records -> %s", count, out_path)
    return count


def parse_holdings(cfg: AppConfig, zip_path: Path) -> int:
    out_path = cfg.sec_13f.processed_dir / "sec_13f_holdings.parquet"
    writer = BatchedParquetWriter(out_path, HOLDING_SCHEMA, cfg.sec_13f.batch_size)

    ingested_at = _ingested_at()
    source_file = zip_path.name
    snapshot_date = _snapshot_date(zip_path)

    con = duckdb.connect()
    extract_stack = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(zip_path) as zf:
        infotable = zf.extract("INFOTABLE.tsv", path=extract_stack.name)
    query = f"""
        SELECT
            ACCESSION_NUMBER AS accession_number,
            INFOTABLE_SK AS infotable_sk,
            NAMEOFISSUER AS name_of_issuer,
            TITLEOFCLASS AS title_of_class,
            CUSIP AS cusip,
            FIGI AS figi,
            TRY_CAST(VALUE AS BIGINT) AS value,
            TRY_CAST(SSHPRNAMT AS DOUBLE) AS shares_or_principal_amount,
            SSHPRNAMTTYPE AS shares_or_principal_type,
            PUTCALL AS put_call,
            INVESTMENTDISCRETION AS investment_discretion,
            OTHERMANAGER AS other_manager,
            TRY_CAST(VOTING_AUTH_SOLE AS BIGINT) AS voting_auth_sole,
            TRY_CAST(VOTING_AUTH_SHARED AS BIGINT) AS voting_auth_shared,
            TRY_CAST(VOTING_AUTH_NONE AS BIGINT) AS voting_auth_none,
        FROM read_csv('{infotable}', delim='\t', header=true, quote='', all_varchar=true)
    """
    started = time.monotonic()
    count = 0
    for batch in con.sql(query).to_arrow_reader(cfg.sec_13f.batch_size):
        for record in batch.to_pylist():
            fields = {
                **record,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
                "ingested_at": ingested_at,
            }
            writer.add(Sec13FHolding(**fields).model_dump())
            count += 1
            if count % LOG_EVERY == 0:
                elapsed = time.monotonic() - started
                logger.info("holdings: %d parsed (%.0fs, %.0f/s)", count, elapsed, count / elapsed)

    writer.close()
    con.close()
    extract_stack.cleanup()
    logger.info("holdings: done, %d records -> %s", count, out_path)
    return count


def _find_zip(cfg: AppConfig) -> Path:
    raw_dir = cfg.sec_13f.raw_dir
    matches = sorted(raw_dir.glob("*_form13f.zip"))
    if not matches:
        raise FileNotFoundError(f"no *_form13f.zip found under {raw_dir}")
    return matches[-1]


def run_all(cfg: AppConfig) -> dict[str, int]:
    """Finds the latest downloaded 13F bulk zip and parses both its tables. Pure
    orchestration, no logging setup/CLI concerns - see er.cli.ingest_sec_13f for
    the command-line entry point."""
    zip_path = _find_zip(cfg)
    logger.info("using %s", zip_path)
    return {
        "filings": parse_filings(cfg, zip_path),
        "holdings": parse_holdings(cfg, zip_path),
    }
