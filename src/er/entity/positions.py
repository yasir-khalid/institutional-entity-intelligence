from __future__ import annotations

from er.serving.store import HOLDINGS, Store


# Above the most rows any manager has reported for one CUSIP across every
# period (1,739), and within OpenSearch's default 10,000-hit window.
MAX_ROWS = 5_000


def load_position_rows(store: Store, cik: str, cusip: str, periods: int = 4) -> list[dict]:
    """Effective 13F information-table rows for one manager and one CUSIP over
    its most recent `periods` report dates, newest first. Option rows are left
    out: a put or call is not a long position in the security."""
    rows = store.find(
        HOLDINGS,
        where={"cik": cik.zfill(10), "cusip": cusip.strip().upper()},
        missing=("put_call",),
        sort=(("period_date", "desc"), ("accession_number", "asc")),
        size=MAX_ROWS,
    )
    rows = [row for row in rows if row.get("value_usd") is not None]
    recent = list(dict.fromkeys(row["period_date"] for row in rows))[:periods]
    return [
        {
            "period_of_report": row["period_of_report"],
            "accession_number": row["accession_number"],
            "infotable_sk": row["infotable_sk"],
            "name_of_issuer": row["name_of_issuer"],
            "value_usd": row["value_usd"],
            "shares": row.get("shares"),
            "shares_type": row.get("shares_type"),
            "source_file": row.get("source_file"),
            "snapshot_date": row.get("snapshot_date"),
            "scale_suspect": bool(row.get("scale_suspect")),
        }
        for row in rows
        if row["period_date"] in recent
    ]
