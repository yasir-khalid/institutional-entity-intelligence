from __future__ import annotations

from er.serving.store import ADV_FIRMS, Store

ADVISER_ID_TYPES = ("crd", "lei", "cik", "name")
SUMMARY_FIELDS = (
    "crd_number", "business_name", "legal_name", "firm_type", "city", "state", "country", "raum", "accounts",
    "employees", "private_fund_count", "private_fund_gross_assets", "fund_types", "lei", "snapshot_date",
)


def search_advisers(
    store: Store,
    query: str | None = None,
    *,
    state: str | None = None,
    firm_type: str | None = None,
    fund_type: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Advisers by name (a phrase in the business or legal name) and filters,
    largest regulatory AUM first."""
    where = {key: value for key, value in (("state", state), ("firm_type", firm_type), ("fund_types", fund_type))
             if value}
    sort = (("raum", "desc"), ("private_fund_gross_assets", "desc"))
    size = offset + limit
    if query and query.strip():
        rows = store.search_text(ADV_FIRMS, query.strip(), field="names", where=where, sort=sort, size=size,
                                 fields=SUMMARY_FIELDS)
    else:
        rows = store.find(ADV_FIRMS, where=where, sort=sort, size=size, fields=SUMMARY_FIELDS)
    return rows[offset:]


def resolve_adviser(store: Store, identifier: str, id_type: str = "crd") -> dict | None:
    if id_type not in ADVISER_ID_TYPES:
        raise ValueError(f"id_type must be one of {', '.join(ADVISER_ID_TYPES)}")
    value = identifier.strip()
    if id_type == "crd":
        return store.get(ADV_FIRMS, value.lstrip("0") or value)
    if id_type == "name":
        rows = store.search_text(ADV_FIRMS, value, field="names", sort=(("raum", "desc"),), size=1)
    else:
        field = {"lei": "lei", "cik": "cik"}[id_type]
        value = value.upper() if id_type == "lei" else value.zfill(10)
        rows = store.find(ADV_FIRMS, where={field: value}, sort=(("raum", "desc"),), size=1)
        if not rows and id_type == "cik":
            rows = store.find(ADV_FIRMS, where={"thirteen_f_cik": value}, sort=(("raum", "desc"),), size=1)
    return rows[0] if rows else None
