from __future__ import annotations

from er.serving.store import FUND_SERIES, Store

FUND_ID_TYPES = ("lei", "cik", "series_id", "class_id", "ticker")


def load_fund_series(store: Store, identifier: str, id_type: str, limit: int = 500) -> list[dict]:
    """The fund series an identifier points at: a registrant's LEI or CIK gives
    all its series, a series LEI or ID one series, a class ID or ticker the
    series that class belongs to. Tickers are reused across classes, so a
    ticker can return more than one series."""
    value = identifier.strip()
    if id_type == "lei":
        either = {"series_lei": value.upper(), "registrant_lei": value.upper()}
        return store.find(FUND_SERIES, either=either, sort=(("series_id", "asc"),), size=limit)
    field, value = {
        "cik": ("cik", value.zfill(10)),
        "series_id": ("series_id", value.upper()),
        "class_id": ("class_ids", value.upper()),
        "ticker": ("tickers", value.upper()),
    }[id_type]
    return store.find(FUND_SERIES, where={field: value}, sort=(("series_id", "asc"),), size=limit)
