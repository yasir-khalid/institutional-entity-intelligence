from __future__ import annotations

from er.serving.store import OWNERSHIP, Store


def load_beneficial_owners(store: Store, issuer_cik: str, limit: int = 25) -> list[dict]:
    """Each reporting person's most recent Schedule 13D/G position in one issuer,
    largest first. An amendment replaces the earlier filing for that person, so
    only the newest one per (person, issuer) is returned."""
    rows = store.find(
        OWNERSHIP,
        where={"issuer_cik": issuer_cik.strip().zfill(10)},
        sort=(("filing_date", "desc"), ("accession_number", "desc")),
        size=1000,
    )
    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(row.get("reporting_person_cik") or row["reporting_person_name"], row)
    owners = sorted(latest.values(), key=lambda row: -(row.get("percent_of_class") or -1))
    return owners[:limit]
