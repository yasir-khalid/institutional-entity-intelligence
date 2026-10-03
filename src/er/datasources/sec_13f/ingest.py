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
from er.datasources.sec_13f.models import Sec13FFiling, Sec13FHolding, Sec13FOtherManager, Sec13FValidation
from er.datasources.sec_13f.schema import FILING_SCHEMA, HOLDING_SCHEMA, OTHER_MANAGER_SCHEMA, VALIDATION_SCHEMA
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


def classify_amendment(is_amendment: bool, amendment_type: str | None) -> str:
    if not is_amendment:
        return "ORIGINAL"
    normalized = (amendment_type or "").strip().upper()
    if normalized == "RESTATEMENT":
        return "REPLACE"
    if normalized == "NEW HOLDINGS":
        return "APPEND"
    return "UNKNOWN"


def validate_summary(
    *,
    accession_number: str,
    filing_date: str | None,
    is_amendment: bool,
    amendment_type: str | None,
    declared_entry_total: int | None,
    observed_entry_total: int,
    declared_value_total: int | None,
    observed_value_total: int,
    provenance: dict,
) -> Sec13FValidation:
    row_count_matches = declared_entry_total == observed_entry_total
    value_total_matches = declared_value_total == observed_value_total
    errors = []
    if not row_count_matches:
        errors.append("TABLE_ENTRY_TOTAL_MISMATCH")
    if not value_total_matches:
        errors.append("TABLE_VALUE_TOTAL_MISMATCH")
    action = classify_amendment(is_amendment, amendment_type)
    if action == "UNKNOWN":
        errors.append("UNKNOWN_AMENDMENT_TYPE")
    parsed_filing_date = None
    if filing_date:
        for date_format in ("%d-%b-%Y", "%Y-%m-%d"):
            try:
                parsed_filing_date = datetime.strptime(filing_date, date_format).date()
                break
            except ValueError:
                continue
    if parsed_filing_date is None:
        errors.append("UNPARSEABLE_FILING_DATE")
    value_unit = "USD" if parsed_filing_date and parsed_filing_date >= datetime(2023, 1, 3).date() else "USD_THOUSANDS"
    return Sec13FValidation(
        accession_number=accession_number,
        declared_entry_total=declared_entry_total,
        observed_entry_total=observed_entry_total,
        declared_value_total=declared_value_total,
        observed_value_total=observed_value_total,
        value_unit=value_unit,
        row_count_matches=row_count_matches,
        value_total_matches=value_total_matches,
        amendment_action=action,
        valid=not errors,
        errors=errors,
        **provenance,
    )


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


def parse_validations(cfg: AppConfig, zip_path: Path) -> int:
    out_path = cfg.sec_13f.processed_dir / "sec_13f_validations.parquet"
    writer = BatchedParquetWriter(out_path, VALIDATION_SCHEMA, cfg.sec_13f.batch_size)
    ingested_at = _ingested_at()
    snapshot_date = _snapshot_date(zip_path)
    provenance = {
        "source_file": zip_path.name,
        "snapshot_date": snapshot_date,
        "ingested_at": ingested_at,
    }
    holdings_path = cfg.sec_13f.processed_dir / "sec_13f_holdings.parquet"

    with _extracted_member(zip_path, "SUMMARYPAGE.tsv") as summary_path:
        con = duckdb.connect()
        query = f"""
            WITH observed AS (
                SELECT accession_number, count(*) observed_entry_total,
                       coalesce(sum(value), 0)::BIGINT observed_value_total
                FROM read_parquet('{holdings_path}') GROUP BY accession_number
            )
            SELECT s.ACCESSION_NUMBER accession_number, f.filing_date,
                   f.is_amendment, f.amendment_type,
                   try_cast(s.TABLEENTRYTOTAL AS BIGINT) declared_entry_total,
                   coalesce(o.observed_entry_total, 0)::BIGINT observed_entry_total,
                   try_cast(s.TABLEVALUETOTAL AS BIGINT) declared_value_total,
                   coalesce(o.observed_value_total, 0)::BIGINT observed_value_total
            FROM read_csv('{summary_path}', delim='\t', header=true, quote='', all_varchar=true) s
            LEFT JOIN read_parquet('{cfg.sec_13f.processed_dir / 'sec_13f_filings.parquet'}') f
                USING (accession_number)
            LEFT JOIN observed o USING (accession_number)
        """
        count = 0
        for batch in con.sql(query).to_arrow_reader(cfg.sec_13f.batch_size):
            for row in batch.to_pylist():
                writer.add(validate_summary(**row, provenance=provenance).model_dump())
                count += 1
        writer.close()
        con.close()
    quarantine_path = cfg.sec_13f.processed_dir / "sec_13f_quarantine.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT * FROM read_parquet('{out_path}') WHERE NOT valid)
        TO '{quarantine_path}' (FORMAT PARQUET)
    """)
    con.close()
    return count


def parse_other_managers(cfg: AppConfig, zip_path: Path) -> int:
    out_path = cfg.sec_13f.processed_dir / "sec_13f_other_managers.parquet"
    writer = BatchedParquetWriter(out_path, OTHER_MANAGER_SCHEMA, cfg.sec_13f.batch_size)
    provenance = {
        "source_file": zip_path.name,
        "snapshot_date": _snapshot_date(zip_path),
        "ingested_at": _ingested_at(),
    }
    with _extracted_member(zip_path, "OTHERMANAGER.tsv") as path:
        con = duckdb.connect()
        query = f"""
            SELECT ACCESSION_NUMBER accession_number, cast(OTHERMANAGER_SK AS VARCHAR) other_manager_sk,
                   CIK cik, FORM13FFILENUMBER form13f_file_number, CRDNUMBER crd_number,
                   SECFILENUMBER sec_file_number, NAME AS "name"
            FROM read_csv('{path}', delim='\t', header=true, quote='', all_varchar=true)
        """
        count = 0
        for batch in con.sql(query).to_arrow_reader(cfg.sec_13f.batch_size):
            for row in batch.to_pylist():
                writer.add(Sec13FOtherManager(**row, **provenance).model_dump())
                count += 1
        writer.close()
        con.close()
    return count


def build_effective_holdings(cfg: AppConfig) -> int:
    processed = cfg.sec_13f.processed_dir
    filings = processed / "sec_13f_filings.parquet"
    holdings = processed / "sec_13f_holdings.parquet"
    validations = processed / "sec_13f_validations.parquet"
    out = processed / "sec_13f_effective_holdings.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            WITH accepted AS (
                SELECT f.*, v.amendment_action, v.value_unit
                FROM read_parquet('{filings}') f
                JOIN read_parquet('{validations}') v USING (accession_number)
                WHERE v.valid
            ), anchors AS (
                SELECT cik, period_of_report,
                       arg_max(accession_number, strptime(filing_date, '%d-%b-%Y')) accession_number,
                       max(strptime(filing_date, '%d-%b-%Y')) anchor_date
                FROM accepted
                WHERE amendment_action IN ('ORIGINAL', 'REPLACE')
                GROUP BY cik, period_of_report
            ), included AS (
                SELECT a.cik, a.period_of_report, f.accession_number, f.value_unit
                FROM anchors a
                JOIN accepted f USING (cik, period_of_report)
                WHERE f.accession_number = a.accession_number
                   OR (f.amendment_action = 'APPEND'
                       AND strptime(f.filing_date, '%d-%b-%Y') >= a.anchor_date)
            )
            SELECT h.*, i.cik, i.period_of_report, i.value_unit,
                   CASE WHEN i.value_unit = 'USD_THOUSANDS' THEN h.value * 1000 ELSE h.value END value_usd
            FROM read_parquet('{holdings}') h JOIN included i USING (accession_number)
        ) TO '{out}' (FORMAT PARQUET)
    """)
    (count,) = con.sql(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()
    con.close()
    return count


def check_value_scale(cfg: AppConfig) -> int:
    """Flags filings made in whole dollars (filed on or after 3 Jan 2023) whose
    values still look like thousands. A row's implied price (value / shares) is
    compared with the median across every filer reporting that CUSIP for the
    same period; a filing whose rows sit near 1/1000 of the consensus is
    flagged. Values are never rescaled - the flag is the evidence."""
    processed = cfg.sec_13f.processed_dir
    effective = processed / "sec_13f_effective_holdings.parquet"
    out = processed / "sec_13f_scale_checks.parquet"
    scale = cfg.sec_13f.scale_check
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            WITH priced AS (
                SELECT accession_number, cik, period_of_report, cusip,
                       value_usd / shares_or_principal_amount AS implied_price
                FROM read_parquet('{effective}')
                WHERE value_unit = 'USD' AND put_call IS NULL AND shares_or_principal_type = 'SH'
                  AND shares_or_principal_amount > 0 AND value_usd > 0
            ), consensus AS (
                SELECT period_of_report, cusip, median(implied_price) AS median_price
                FROM priced GROUP BY ALL HAVING count(DISTINCT cik) >= {scale.min_filers_per_cusip}
            )
            SELECT accession_number, any_value(cik) AS cik, any_value(period_of_report) AS period_of_report,
                   count(*) AS compared_rows,
                   median(p.implied_price / c.median_price) AS median_price_ratio,
                   count(*) >= {scale.min_rows}
                       AND median(p.implied_price / c.median_price)
                           BETWEEN {scale.thousands_ratio_low} AND {scale.thousands_ratio_high}
                       AS looks_like_thousands
            FROM priced p JOIN consensus c USING (period_of_report, cusip)
            GROUP BY accession_number
        ) TO '{out}' (FORMAT PARQUET)
    """)
    (flagged,) = con.sql(f"SELECT count(*) FROM read_parquet('{out}') WHERE looks_like_thousands").fetchone()
    con.close()
    return flagged


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
    filings = parse_filings(cfg, zip_path)
    holdings = parse_holdings(cfg, zip_path)
    validations = parse_validations(cfg, zip_path)
    other_managers = parse_other_managers(cfg, zip_path)
    return {
        "filings": filings,
        "holdings": holdings,
        "validations": validations,
        "other_managers": other_managers,
        "effective_holdings": build_effective_holdings(cfg),
        "scale_suspect_filings": check_value_scale(cfg),
    }
