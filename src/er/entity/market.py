"""Per-security reads: who reports holding it on 13F, and its short sale
volume and fails-to-deliver. A security is found by CUSIP or ticker; the
ticker comes from OpenFIGI (13F CUSIPs) or from SEC's fails file."""

from __future__ import annotations

import re

from er.knowledge.formulas import FORMULAS
from er.serving.store import FAILS_TO_DELIVER, SECURITY_OWNERSHIP, SHORT_VOLUME, Store

_CUSIP = re.compile(r"^[0-9A-Z]{8}[0-9]$")


def resolve_security(store: Store, identifier: str) -> dict | None:
    """{cusip, symbol} for a CUSIP or ticker; either may be None."""
    value = identifier.strip().upper()
    if _CUSIP.match(value) and any(char.isdigit() for char in value[:8]):
        owned = store.get(SECURITY_OWNERSHIP, value, fields=("tickers",))
        fails = store.get(FAILS_TO_DELIVER, value, fields=("symbol",))
        tickers = (owned or {}).get("tickers") or []
        symbol = (fails or {}).get("symbol") or (tickers[0] if tickers else None)
        return {"cusip": value, "symbol": symbol} if owned or fails else None
    owned = store.find(SECURITY_OWNERSHIP, where={"tickers": value}, sort=(("holder_count", "desc"),), size=1,
                       fields=("cusip",))
    fails = store.find(FAILS_TO_DELIVER, where={"symbol": value}, size=1, fields=("cusip",))
    cusip = (owned or fails or [{}])[0].get("cusip")
    if cusip or store.get(SHORT_VOLUME, value, fields=("symbol",)):
        return {"cusip": cusip, "symbol": value}
    return None


SUMMARY_FIELDS = ("cusip", "issuer_name", "title_of_class", "tickers", "holder_count", "latest_period")


def search_securities(store: Store, query: str | None, limit: int = 10) -> list[dict]:
    """By CUSIP, ticker or issuer name; with no query, the most widely held."""
    fields = SUMMARY_FIELDS
    if not query or not query.strip():
        return store.find(SECURITY_OWNERSHIP, sort=(("holder_count", "desc"),), size=limit, fields=fields)
    resolved = resolve_security(store, query)
    if resolved and resolved["cusip"]:
        doc = store.get(SECURITY_OWNERSHIP, resolved["cusip"], fields=fields)
        if doc:
            return [doc]
    return store.search_text(SECURITY_OWNERSHIP, query.strip(), field="issuer_name",
                             sort=(("holder_count", "desc"),), size=limit, fields=fields)


def _change(current: float | None, previous: float | None) -> dict:
    if current is None or previous is None:
        return {"change": None, "percent_change": None}
    return {
        "change": FORMULAS["difference"].compute(current, previous),
        "percent_change": FORMULAS["percent_change"].compute(current, previous),
    }


def load_ownership(store: Store, cusip: str, limit: int = 100) -> dict | None:
    """The CUSIP's 13F ownership document, each holder carrying its share
    change since the previous period (difference and percent_change from
    er.knowledge.formulas; None when the holder reported nothing before)."""
    doc = store.get(SECURITY_OWNERSHIP, cusip.strip().upper())
    if not doc:
        return None
    holders = []
    for holder in doc.get("holders", [])[:limit]:
        new = holder.get("previous_shares") is None and doc.get("previous_period") is not None
        holders.append({**holder, **_change(holder.get("shares"), holder.get("previous_shares")), "new": new})
    return {**doc, "holders": holders}


def load_short_volume(store: Store, symbol: str, days: int = 30) -> list[dict]:
    doc = store.get(SHORT_VOLUME, symbol.strip().upper())
    rows = (doc or {}).get("days", [])[-days:]
    return [{**row, "short_ratio": FORMULAS["percent_of"].compute(row["short_volume"], row["total_volume"])}
            for row in rows]


def load_fails(store: Store, cusip: str, limit: int = 60) -> dict | None:
    doc = store.get(FAILS_TO_DELIVER, cusip.strip().upper())
    if not doc:
        return None
    return {**doc, "fails": doc.get("fails", [])[-limit:]}
