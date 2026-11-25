from __future__ import annotations

from datetime import date, timedelta

from er.serving.store import FORM_D, Store

LIST_FIELDS = (
    "accession_number", "filing_date", "submission_type", "is_amendment", "issuer_cik", "issuer_name", "city",
    "state", "industry_group", "fund_type", "is_fund", "total_offering", "offering_indefinite", "total_sold",
    "investor_count", "minimum_investment",
)


def latest_filing_date(store: Store) -> str | None:
    rows = store.find(FORM_D, sort=(("filing_date", "desc"),), size=1, fields=("filing_date",))
    return rows[0]["filing_date"] if rows else None


def search_offerings(
    store: Store,
    query: str | None = None,
    *,
    kind: str | None = None,
    fund_type: str | None = None,
    industry: str | None = None,
    state: str | None = None,
    days: int | None = None,
    new_only: bool = False,
    sort: str = "newest",
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], dict]:
    """Form D filings, newest first or (sort="largest") by amount sold.
    `days` counts back from the newest filing in the data, not from today -
    the data set is published quarterly."""
    where: dict = {}
    if kind in ("fund", "company"):
        where["is_fund"] = kind == "fund"
    for field, value in (("fund_type", fund_type), ("industry_group", industry), ("state", state)):
        if value:
            where[field] = value
    if new_only:
        where["is_amendment"] = False
    window: dict = {}
    if days:
        newest = latest_filing_date(store)
        if newest:
            end = date.fromisoformat(newest)
            where["filing_date"] = [(end - timedelta(days=offset_days)).isoformat() for offset_days in range(days)]
            window = {"from": (end - timedelta(days=days - 1)).isoformat(), "to": newest}
    order = (("filing_date", "desc"), ("total_sold", "desc"))
    if sort == "largest":
        order = order[::-1]
    size = offset + limit
    if query and query.strip():
        text = query.strip()
        rows = store.search_text(FORM_D, text, field="issuer_name", where=where, sort=order, size=size,
                                 fields=LIST_FIELDS)
        if not rows:
            rows = store.search_text(FORM_D, text, field="people_names", where=where, sort=order, size=size,
                                     fields=LIST_FIELDS)
    else:
        rows = store.find(FORM_D, where=where, sort=order, size=size, fields=LIST_FIELDS)
    return rows[offset:], window


def load_offering(store: Store, accession_number: str) -> dict | None:
    return store.get(FORM_D, accession_number.strip())
