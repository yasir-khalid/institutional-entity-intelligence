"""Validation checks over the processed GLEIF Parquet tables, via DuckDB.

Run after ingestion (er.datasources.gleif.ingest) to catch data-quality problems before they
propagate into search/benchmarking: malformed identifiers, unexpected duplicates,
and how well relationships/exceptions/ISIN mappings line up with the entities table.

DuckDB queries the Parquet files directly (no manual load-into-memory / pyarrow
Acero join workarounds needed) and can spill to disk for tables larger than RAM.
"""

from __future__ import annotations

import json
import logging
import sys

import duckdb

from er.config import AppConfig, load_config

logger = logging.getLogger(__name__)

LEI_REGEX = r"^[0-9A-Z]{18}[0-9]{2}$"
ISIN_REGEX = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"


def _null_rates(con: duckdb.DuckDBPyConnection, path) -> dict[str, float]:
    rel = con.sql(f"SUMMARIZE SELECT * FROM read_parquet('{path}')")
    columns = rel.columns
    name_idx = columns.index("column_name")
    null_pct_idx = columns.index("null_percentage")
    return {row[name_idx]: round(float(row[null_pct_idx] or 0) / 100, 4) for row in rel.fetchall()}


def _duplicate_count(con: duckdb.DuckDBPyConnection, path, key_columns: list[str]) -> int:
    cols = ", ".join(key_columns)
    query = f"""
        SELECT COALESCE(SUM(c - 1), 0)
        FROM (
            SELECT COUNT(*) AS c
            FROM read_parquet('{path}')
            GROUP BY {cols}
            HAVING COUNT(*) > 1
        )
    """
    return int(con.sql(query).fetchone()[0])


def validate_entities(con: duckdb.DuckDBPyConnection, cfg: AppConfig, report: dict) -> None:
    path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    row_count, duplicate_leis, malformed_leis = con.sql(f"""
        SELECT
            COUNT(*),
            COUNT(*) - COUNT(DISTINCT lei),
            SUM(CASE WHEN NOT regexp_matches(lei, '{LEI_REGEX}') THEN 1 ELSE 0 END)
        FROM read_parquet('{path}')
    """).fetchone()

    report["entities"] = {
        "row_count": row_count,
        "duplicate_lei_count": duplicate_leis,
        "malformed_lei_count": malformed_leis,
        "null_rates": _null_rates(con, path),
    }
    if duplicate_leis:
        report.setdefault("hard_failures", []).append(f"entities: {duplicate_leis} duplicate LEIs")
    if malformed_leis:
        report.setdefault("hard_failures", []).append(f"entities: {malformed_leis} malformed LEIs")


def validate_relationships(con: duckdb.DuckDBPyConnection, cfg: AppConfig, report: dict) -> None:
    rel_path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    entities_path = cfg.gleif.processed_dir / "gleif_entities.parquet"

    row_count, start_null, end_null = con.sql(f"""
        SELECT
            COUNT(*),
            SUM(CASE WHEN start_node_id IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN end_node_id IS NULL THEN 1 ELSE 0 END)
        FROM read_parquet('{rel_path}')
    """).fetchone()

    lei_endpoints, lei_endpoints_found = con.sql(f"""
        WITH endpoints AS (
            SELECT start_node_id AS id, start_node_id_type AS id_type FROM read_parquet('{rel_path}')
            UNION ALL
            SELECT end_node_id, end_node_id_type FROM read_parquet('{rel_path}')
        )
        SELECT
            COUNT(*) FILTER (WHERE id_type = 'LEI'),
            COUNT(*) FILTER (WHERE id_type = 'LEI' AND id IN (SELECT lei FROM read_parquet('{entities_path}')))
        FROM endpoints
    """).fetchone()

    coverage = round(lei_endpoints_found / lei_endpoints, 4) if lei_endpoints else None
    duplicates = _duplicate_count(con, rel_path, ["start_node_id", "end_node_id", "relationship_type"])

    report["relationships"] = {
        "row_count": row_count,
        "start_node_id_null_count": start_null,
        "end_node_id_null_count": end_null,
        "lei_endpoint_coverage": coverage,
        "duplicate_count": duplicates,
        "null_rates": _null_rates(con, rel_path),
    }
    if start_null or end_null:
        report.setdefault("hard_failures", []).append(
            f"relationships: {start_null} null start_node_id, {end_null} null end_node_id"
        )


def validate_relationship_exceptions(con: duckdb.DuckDBPyConnection, cfg: AppConfig, report: dict) -> None:
    path = cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet"
    entities_path = cfg.gleif.processed_dir / "gleif_entities.parquet"

    row_count, found = con.sql(f"""
        SELECT
            COUNT(*),
            COUNT(*) FILTER (WHERE lei IN (SELECT lei FROM read_parquet('{entities_path}')))
        FROM read_parquet('{path}')
    """).fetchone()

    coverage = round(found / row_count, 4) if row_count else None
    duplicates = _duplicate_count(con, path, ["lei", "exception_category", "exception_reason"])

    report["relationship_exceptions"] = {
        "row_count": row_count,
        "lei_coverage": coverage,
        "duplicate_count": duplicates,
        "null_rates": _null_rates(con, path),
    }


def validate_isin_lei(con: duckdb.DuckDBPyConnection, cfg: AppConfig, report: dict) -> None:
    path = cfg.gleif.processed_dir / "isin_lei.parquet"
    entities_path = cfg.gleif.processed_dir / "gleif_entities.parquet"

    row_count, malformed_isins, found = con.sql(f"""
        SELECT
            COUNT(*),
            SUM(CASE WHEN NOT regexp_matches(isin, '{ISIN_REGEX}') THEN 1 ELSE 0 END),
            COUNT(*) FILTER (WHERE lei IN (SELECT lei FROM read_parquet('{entities_path}')))
        FROM read_parquet('{path}')
    """).fetchone()

    coverage = round(found / row_count, 4) if row_count else None
    duplicates = _duplicate_count(con, path, ["isin", "lei"])

    report["isin_lei"] = {
        "row_count": row_count,
        "malformed_isin_count": malformed_isins,
        "lei_coverage": coverage,
        "duplicate_count": duplicates,
        "null_rates": _null_rates(con, path),
    }


def validate_all(cfg: AppConfig) -> dict:
    report: dict = {}
    con = duckdb.connect()
    try:
        validate_entities(con, cfg, report)
        validate_relationships(con, cfg, report)
        validate_relationship_exceptions(con, cfg, report)
        validate_isin_lei(con, cfg, report)
    finally:
        con.close()
    report.setdefault("hard_failures", [])
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    report = validate_all(cfg)

    out_path = cfg.gleif.processed_dir / "validation_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    logger.info("validation report written to %s", out_path)

    for table_name, stats in report.items():
        if table_name == "hard_failures":
            continue
        logger.info("%s: %s", table_name, {k: v for k, v in stats.items() if k != "null_rates"})

    if report["hard_failures"]:
        logger.error("hard failures: %s", report["hard_failures"])
        sys.exit(1)
    logger.info("validation passed with no hard failures")


if __name__ == "__main__":
    main()
