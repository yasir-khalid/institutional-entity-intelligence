"""Comparison features between a query record and a single GLEIF candidate.

Each function takes the same two dicts and returns one signal - independently
readable, independently testable, independently droppable if a signal turns out
not to help. A `None` return means "no signal" (the query lacks that field), not
"mismatch" - conflict features are the exception, since a conflict can only be
detected when *both* sides carry the relevant flag.

`query` fields (build with `build_query_record` below): name, name_norm, name_core,
country, postcode, postcode_prefix, city, registration_id, fund_number, is_master,
is_feeder.

`candidate` fields: whatever `er.retrieval.candidates.search_candidates` returns -
i.e. the indexed document (legal_name, legal_name_norm, legal_name_core,
legal_country, jurisdiction, legal_postcode, legal_city, registration_id,
fund_number, is_master, is_feeder, ...).
"""

from __future__ import annotations

from rapidfuzz import fuzz

from er.normalisation.addresses import normalize_postcode, postcode_outward
from er.normalisation.countries import country_from_jurisdiction
from er.normalisation.names import build_name_fields


def build_query_record(
    name: str,
    country: str | None = None,
    postcode: str | None = None,
    city: str | None = None,
    registration_id: str | None = None,
) -> dict:
    """Turn raw query inputs into the record shape features.py expects, deriving
    name_norm/name_core/fund_number/is_master/is_feeder via the same normalization
    used at ingestion time (er.normalisation.names.build_name_fields)."""
    name_fields = build_name_fields(name)
    postcode_norm = normalize_postcode(postcode)
    return {
        "name": name,
        "name_norm": name_fields["legal_name_norm"],
        "name_core": name_fields["legal_name_core"],
        "fund_number": name_fields["fund_number"],
        "is_master": name_fields["is_master"],
        "is_feeder": name_fields["is_feeder"],
        "country": country,
        "postcode": postcode_norm,
        "postcode_prefix": postcode_outward(postcode_norm) if postcode_norm else None,
        "city": city,
        "registration_id": registration_id,
    }


def name_exact(query: dict, candidate: dict) -> bool:
    return query["name_norm"] == candidate.get("legal_name_norm")


def name_core_exact(query: dict, candidate: dict) -> bool:
    return bool(query["name_core"]) and query["name_core"] == candidate.get("legal_name_core")


def name_ratio(query: dict, candidate: dict) -> float:
    """rapidfuzz ratio (0-1) between normalized names."""
    candidate_name = candidate.get("legal_name_norm") or ""
    if not query["name_norm"] or not candidate_name:
        return 0.0
    return fuzz.ratio(query["name_norm"], candidate_name) / 100.0


def country_exact(query: dict, candidate: dict) -> bool | None:
    """Bare-country match, tolerant of either side being a full jurisdiction code
    (e.g. "US-DE") by taking just the country prefix."""
    if not query.get("country"):
        return None
    q = country_from_jurisdiction(query["country"])
    c = country_from_jurisdiction(candidate.get("legal_country"))
    if not q or not c:
        return None
    return q == c


def jurisdiction_exact(query: dict, candidate: dict) -> bool | None:
    if not query.get("country"):
        return None
    return query["country"].strip().upper() == (candidate.get("jurisdiction") or "").upper()


def postcode_exact(query: dict, candidate: dict) -> bool | None:
    if not query.get("postcode"):
        return None
    return query["postcode"] == candidate.get("legal_postcode")


def postcode_prefix_exact(query: dict, candidate: dict) -> bool | None:
    if not query.get("postcode_prefix"):
        return None
    candidate_prefix = postcode_outward(candidate.get("legal_postcode"))
    if not candidate_prefix:
        return None
    return query["postcode_prefix"] == candidate_prefix


def city_exact(query: dict, candidate: dict) -> bool | None:
    if not query.get("city"):
        return None
    return query["city"].strip().lower() == (candidate.get("legal_city") or "").lower()


def registration_id_exact(query: dict, candidate: dict) -> bool | None:
    if not query.get("registration_id"):
        return None
    return query["registration_id"] == candidate.get("registration_id")


def fund_number_exact(query: dict, candidate: dict) -> bool | None:
    if query.get("fund_number") is None or candidate.get("fund_number") is None:
        return None
    return query["fund_number"] == candidate["fund_number"]


def fund_number_conflict(query: dict, candidate: dict) -> bool:
    """True only when BOTH sides have a fund number and they differ - the
    "Fund II vs Fund III" case. Absence of a fund number on either side is not a
    conflict (most entities aren't part of a numbered series at all)."""
    q, c = query.get("fund_number"), candidate.get("fund_number")
    return q is not None and c is not None and q != c


def master_conflict(query: dict, candidate: dict) -> bool:
    """True when exactly one side claims to be a master fund - if neither does,
    != is already False, so no extra "at least one is True" check is needed."""
    return bool(query.get("is_master")) != bool(candidate.get("is_master"))


def feeder_conflict(query: dict, candidate: dict) -> bool:
    return bool(query.get("is_feeder")) != bool(candidate.get("is_feeder"))


def registration_id_conflict(query: dict, candidate: dict) -> bool:
    """True when both sides have a registration id and they differ - unlike
    fund/master/feeder conflicts this is a very strong negative signal (registration
    numbers are unique within a registry)."""
    q, c = query.get("registration_id"), candidate.get("registration_id")
    return bool(q) and bool(c) and q != c


# Every feature function, in the order features are computed - scoring.py iterates
# this list so adding a new feature only ever means adding one function here.
FEATURE_FUNCTIONS = {
    "name_exact": name_exact,
    "name_core_exact": name_core_exact,
    "name_ratio": name_ratio,
    "country_exact": country_exact,
    "jurisdiction_exact": jurisdiction_exact,
    "postcode_exact": postcode_exact,
    "postcode_prefix_exact": postcode_prefix_exact,
    "city_exact": city_exact,
    "registration_id_exact": registration_id_exact,
    "fund_number_exact": fund_number_exact,
    "fund_number_conflict": fund_number_conflict,
    "master_conflict": master_conflict,
    "feeder_conflict": feeder_conflict,
    "registration_id_conflict": registration_id_conflict,
}


def compute_features(query: dict, candidate: dict) -> dict:
    return {name: fn(query, candidate) for name, fn in FEATURE_FUNCTIONS.items()}
