from __future__ import annotations

from er.serving.store import SECURITIES, Store

SECURITY_ID_TYPES = ("cusip", "ticker", "figi")


def load_securities(store: Store, identifier: str, id_type: str, limit: int = 25) -> list[dict]:
    """OpenFIGI's mapping for the 13F CUSIPs an identifier points at - one
    CUSIP directly, or every CUSIP whose securities carry this ticker or FIGI."""
    value = identifier.strip().upper()
    if id_type == "cusip":
        doc = store.get(SECURITIES, value)
        return [doc] if doc else []
    field = {"ticker": "tickers", "figi": "figis"}[id_type]
    return store.find(SECURITIES, where={field: value}, sort=(("cusip", "asc"),), size=limit)
