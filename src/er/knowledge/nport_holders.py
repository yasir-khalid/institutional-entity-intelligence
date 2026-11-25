"""Reverse N-PORT holder lookup.

The agent's N-PORT serving index is fund-centric: it answers "what does this
fund hold?" but not "who holds this issuer's bond?" This module reads the
processed N-PORT Parquet tables directly and returns the reverse view. Parquet
is the build store; in a multi-replica deployment this should become a serving
index, but the query shape and evidence contract stay the same.

Scope: registered funds only, latest N-PORT snapshot per fund series, fair
value at the report date. It is not a legal ownership register and not the
issuer's full debt stack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from er.config import AppConfig

NPORT_WARNING = (
    "Form N-PORT is a dated monthly snapshot made public with a 60-day lag; "
    "values are fund-level fair values, not original allocation. Registered "
    "funds only: private funds, separate accounts and non-fund holders are absent."
)
NPORT_SOURCE_URI = "https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets"


def find_nport_holders(
    cfg: AppConfig,
    identifier: str,
    *,
    id_type: str = "name",
    limit: int = 25,
) -> dict[str, Any]:
    """Return fund reports and registrants holding an issuer's N-PORT security.

    id_type is "name" (issuer name, case-insensitive substring) or "cusip"
    (exact issuer CUSIP). The result is grouped by fund report, then by
    registrant, so a fund family with many series is visible without double
    counting the same report.
    """
    if id_type not in {"name", "cusip"}:
        raise ValueError('id_type must be "name" or "cusip"')
    limit = max(1, min(int(limit), 100))
    processed = Path(cfg.entity.processed_dir)
    holdings = processed / "nport_holdings.parquet"
    funds = processed / "nport_funds.parquet"
    if not holdings.exists() or not funds.exists():
        return {
            "found": False,
            "identifier": identifier,
            "id_type": id_type,
            "reason": "N-PORT processed tables are not installed",
            "warnings": [NPORT_WARNING],
        }

    if id_type == "cusip":
        where = "h.issuer_cusip = ?"
        param = identifier.strip().upper()
    else:
        where = "lower(h.issuer_name) LIKE '%' || lower(?) || '%'"
        param = identifier.strip()

    con = duckdb.connect()
    try:
        rows = con.execute(
            f"""
            SELECT f.registrant_name, f.series_name, f.accession_number, f.report_date,
                   f.filing_date, h.issuer_name, h.issuer_title, h.issuer_cusip,
                   sum(h.currency_value) AS value_usd,
                   count(*) AS holding_rows
            FROM read_parquet('{holdings}') h
            JOIN read_parquet('{funds}') f USING (accession_number)
            WHERE {where}
            GROUP BY ALL
            ORDER BY value_usd DESC
            LIMIT ?
            """,
            [param, limit],
        ).fetchall()
        aggregate = con.execute(
            f"""
            SELECT count(DISTINCT f.accession_number) AS fund_reports,
                   count(DISTINCT f.registrant_name) AS registrants,
                   sum(h.currency_value) AS total_value_usd
            FROM read_parquet('{holdings}') h
            JOIN read_parquet('{funds}') f USING (accession_number)
            WHERE {where}
            """,
            [param],
        ).fetchone()
        by_registrant = con.execute(
            f"""
            SELECT f.registrant_name,
                   count(DISTINCT f.accession_number) AS fund_reports,
                   sum(h.currency_value) AS value_usd
            FROM read_parquet('{holdings}') h
            JOIN read_parquet('{funds}') f USING (accession_number)
            WHERE {where}
            GROUP BY 1
            ORDER BY value_usd DESC
            LIMIT ?
            """,
            [param, limit],
        ).fetchall()
    finally:
        con.close()

    fund_reports = int(aggregate[0] or 0) if aggregate else 0
    if not rows:
        return {
            "found": False,
            "identifier": identifier,
            "id_type": id_type,
            "fund_reports": 0,
            "registrants": 0,
            "reported_value_usd": 0.0,
            "holders": [],
            "by_registrant": [],
            "warnings": [NPORT_WARNING],
            "source_uri": NPORT_SOURCE_URI,
        }

    holders = [
        {
            "registrant_name": r[0],
            "series_name": r[1],
            "accession_number": r[2],
            "report_date": r[3],
            "filing_date": r[4],
            "issuer_name": r[5],
            "issuer_title": r[6],
            "cusip": r[7],
            "value_usd": float(r[8] or 0),
            "holding_rows": int(r[9] or 0),
        }
        for r in rows
    ]
    return {
        "found": True,
        "identifier": identifier,
        "id_type": id_type,
        "fund_reports": fund_reports,
        "registrants": int(aggregate[1] or 0) if aggregate else 0,
        "reported_value_usd": float(aggregate[2] or 0) if aggregate else 0.0,
        "holders": holders,
        "by_registrant": [
            {"registrant_name": r[0], "fund_reports": int(r[1] or 0), "value_usd": float(r[2] or 0)}
            for r in by_registrant
        ],
        "warnings": [NPORT_WARNING],
        "source_uri": NPORT_SOURCE_URI,
    }
