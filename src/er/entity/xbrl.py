"""Read side for SEC XBRL company facts (see er.datasources.sec_xbrl).

Two things make this layer different from every other entity read: a series is
kept whole (every dated observation, not just the latest), and every observation
carries the filing date it was reported on (`filed`). That lets a caller ask
what was knowable on a given date - the point-in-time question - instead of only
what the most recent filing says. A single balance-sheet identity
(Assets = LiabilitiesAndStockholdersEquity) is checked here, so a mis-parsed or
inconsistent series is visible rather than silently returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from er.serving.store import XBRL_FACTS, XBRL_ISSUERS, Store

# XBRL states a unit as a formula string; the rest of the platform speaks a
# small vocabulary, so a stored "USD/shares" travels as "USD_per_share" and a
# unitless measure ("pure") as "ratio".
_UNITS = {"USD": "USD", "shares": "shares", "USD/shares": "USD_per_share", "pure": "ratio"}

_INVARIANT_TOLERANCE = 0.005  # 0.5% of the larger side


def normalise_unit(xbrl_unit: str) -> str:
    return _UNITS.get(xbrl_unit, xbrl_unit)


def cik_of(identifier: str) -> str:
    return (str(identifier or "").strip().lstrip("0") or "0").zfill(10)


@dataclass(frozen=True)
class Series:
    cik: str
    entity_name: str
    tag: str
    unit: str
    observations: list[dict]

    @classmethod
    def from_document(cls, doc: dict) -> "Series":
        observations = sorted(
            doc.get("observations") or [],
            key=lambda row: (row.get("period_end") or "", row.get("filed") or ""),
        )
        return cls(
            cik=doc["cik"],
            entity_name=doc.get("entity_name") or doc["cik"],
            tag=doc["tag"],
            unit=doc.get("unit") or "",
            observations=observations,
        )


def resolve_issuer(store: Store, identifier: str, id_type: str = "cik") -> dict | None:
    """Resolve an issuer to its CIK by CIK, ticker or name. Returns None when
    nothing matches - the caller reports that, it never guesses a CIK."""
    id_type = (id_type or "cik").lower()
    if id_type == "cik":
        return store.get(XBRL_ISSUERS, cik_of(identifier))
    if id_type == "ticker":
        matches = store.find(XBRL_ISSUERS, where={"tickers": identifier.strip().upper()}, size=2)
    elif id_type == "name":
        matches = store.search_text(XBRL_ISSUERS, identifier, field="entity_name", size=5)
    else:
        raise ValueError(f"Unknown id_type {id_type!r}; expected cik, ticker or name")
    return matches[0] if matches else None


def load_series(store: Store, cik: str) -> list[Series]:
    documents = store.find(XBRL_FACTS, where={"cik": cik_of(cik)}, size=200, sort=(("tag", "asc"),))
    return [Series.from_document(doc) for doc in documents]


def known_on(observations: list[dict], as_of: str | None) -> list[dict]:
    """The series as it was knowable on `as_of`: drop observations for periods
    that had not ended yet, and for any given period keep only the value from
    the latest filing on or before the date. Without an as-of, the whole series
    is returned unchanged."""
    if not as_of:
        return list(observations)
    chosen: dict[tuple, dict] = {}
    for row in observations:
        if (row.get("period_end") or "") > as_of or (row.get("filed") or "") > as_of:
            continue
        key = (row.get("period_start"), row.get("period_end"))
        current = chosen.get(key)
        if current is None or (row.get("filed") or "") >= (current.get("filed") or ""):
            chosen[key] = row
    return sorted(chosen.values(), key=lambda row: (row.get("period_end") or "", row.get("filed") or ""))


def latest(observations: list[dict], as_of: str | None = None) -> dict | None:
    rows = known_on(observations, as_of)
    return rows[-1] if rows else None


def balance_check(series: list[Series], as_of: str | None = None) -> dict | None:
    """The one accounting identity a balance sheet cannot violate:
    Assets = LiabilitiesAndStockholdersEquity. Returns None when the series
    doesn't carry both sides, so a caller never reads "checked" as "passed"."""
    by_tag = {item.tag: item for item in series}
    assets = latest(by_tag["Assets"].observations, as_of) if "Assets" in by_tag else None
    total = latest(by_tag["LiabilitiesAndStockholdersEquity"].observations, as_of) if \
        "LiabilitiesAndStockholdersEquity" in by_tag else None
    if assets is None or total is None:
        return None
    residual = float(assets["value"]) - float(total["value"])
    scale = max(abs(float(assets["value"])), abs(float(total["value"])), 1.0)
    return {
        "identity": "Assets = LiabilitiesAndStockholdersEquity",
        "period_end": assets.get("period_end"),
        "assets": float(assets["value"]),
        "liabilities_and_equity": float(total["value"]),
        "residual": residual,
        "passed": abs(residual) <= _INVARIANT_TOLERANCE * scale,
    }
