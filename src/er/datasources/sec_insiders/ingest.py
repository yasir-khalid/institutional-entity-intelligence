from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import InsiderRelationship, InsiderTransaction
from .schema import RELATIONSHIP_SCHEMA, TRANSACTION_SCHEMA


TABLES = ("SUBMISSION.tsv", "REPORTINGOWNER.tsv", "NONDERIV_TRANS.tsv", "DERIV_TRANS.tsv")


def _read(path: Path) -> str:
    return f"read_csv('{path}', delim='\\t', header=true, quote='', all_varchar=true)"


def _write_rows(cfg, query, writer, model, provenance) -> int:
    con = duckdb.connect()
    count = 0
    for batch in con.sql(query).to_arrow_reader(cfg.sec_insiders.batch_size):
        for row in batch.to_pylist():
            writer.add(model(**row, **provenance).model_dump())
            count += 1
    con.close()
    return count


def _writers(cfg: AppConfig) -> dict[str, BatchedParquetWriter]:
    out, size = cfg.sec_insiders.processed_dir, cfg.sec_insiders.batch_size
    return {
        "relationships": BatchedParquetWriter(out / "sec_insider_relationships.parquet", RELATIONSHIP_SCHEMA, size),
        "transactions": BatchedParquetWriter(out / "sec_insider_transactions.parquet", TRANSACTION_SCHEMA, size),
    }


def parse_zip(cfg: AppConfig, path: Path, writers: dict[str, BatchedParquetWriter]) -> dict[str, int]:
    provenance = {
        "source_file": path.name,
        "snapshot_date": path.stem.split("_")[0],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as archive:
            paths = {name: Path(archive.extract(name, path=tmp)) for name in TABLES}

        relationships = _write_rows(
            cfg,
            f"""
                SELECT s.ACCESSION_NUMBER accession_number, s.FILING_DATE filing_date,
                       s.PERIOD_OF_REPORT period_of_report, s.DOCUMENT_TYPE document_type,
                       s.ISSUERCIK issuer_cik, s.ISSUERNAME issuer_name,
                       s.ISSUERTRADINGSYMBOL issuer_ticker, o.RPTOWNERCIK owner_cik,
                       o.RPTOWNERNAME owner_name, o.RPTOWNER_RELATIONSHIP relationship,
                       o.RPTOWNER_TITLE owner_title
                FROM {_read(paths['SUBMISSION.tsv'])} s
                JOIN {_read(paths['REPORTINGOWNER.tsv'])} o USING (ACCESSION_NUMBER)
            """,
            writers["relationships"],
            InsiderRelationship,
            provenance,
        )

        transaction_parts = []
        for table, key, derivative in (
            ("NONDERIV_TRANS.tsv", "NONDERIV_TRANS_SK", False),
            ("DERIV_TRANS.tsv", "DERIV_TRANS_SK", True),
        ):
            transaction_parts.append(f"""
                SELECT t.ACCESSION_NUMBER accession_number, cast(t.{key} AS VARCHAR) transaction_id,
                       o.RPTOWNERCIK owner_cik, s.ISSUERCIK issuer_cik,
                       t.SECURITY_TITLE security_title, t.TRANS_DATE transaction_date,
                       t.TRANS_CODE transaction_code, t.TRANS_ACQUIRED_DISP_CD acquired_disposed,
                       try_cast(t.TRANS_SHARES AS DOUBLE) shares,
                       try_cast(t.TRANS_PRICEPERSHARE AS DOUBLE) price_per_share,
                       try_cast(t.SHRS_OWND_FOLWNG_TRANS AS DOUBLE) shares_following,
                       t.DIRECT_INDIRECT_OWNERSHIP direct_indirect, {str(derivative).lower()} derivative
                FROM {_read(paths[table])} t
                JOIN {_read(paths['SUBMISSION.tsv'])} s USING (ACCESSION_NUMBER)
                JOIN {_read(paths['REPORTINGOWNER.tsv'])} o USING (ACCESSION_NUMBER)
            """)
        transactions = _write_rows(
            cfg,
            " UNION ALL ".join(transaction_parts),
            writers["transactions"],
            InsiderTransaction,
            provenance,
        )
    return {"relationships": relationships, "transactions": transactions}


def run_all(cfg: AppConfig) -> dict[str, int]:
    source = cfg.sec_insiders
    download_if_missing(source.source_url, source.raw_dir / source.source_file)
    for url in source.history_urls:
        download_if_missing(url, source.raw_dir / url.rsplit("/", 1)[-1])
    writers = _writers(cfg)
    totals = {"relationships": 0, "transactions": 0}
    for path in sorted(source.raw_dir.glob("*_form345.zip")):
        for name, count in parse_zip(cfg, path, writers).items():
            totals[name] += count
    for writer in writers.values():
        writer.close()
    return totals
