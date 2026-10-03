"""Assembles one EntityProfile: canonical identity + attached identifiers +
GLEIF relationship neighborhood + SEC 13F activity summary (when available).

This is the single place a profile is put together - er.cli.entity, the API
and the agent tools all call get_entity_profile() rather than re-deriving it.
The heavy joins happen once, at publish time (er.serving.publish); here it is
an entity document, its 13F filer document, and the hierarchy lookups.
"""

from __future__ import annotations

from er.entity.models import (
    EntityIdentifier,
    EntityLineage,
    EntityProfile,
    Sec13FActivity,
    Sec13FHoldingSummary,
)
from er.graph.build import build_hierarchy
from er.serving.store import ENTITIES, FILERS, Store


PROFILE_FIELDS = (
    "entity_id", "canonical_name", "entity_type", "jurisdiction", "legal_country", "entity_status",
    "entity_creation_date", "initial_registration_date", "last_update_date", "next_renewal_date",
    "registration_status", "gleif_snapshot_date", "identifiers", "identifier_total", "ciks",
)


def load_sec_13f_activity(store: Store, cik: str) -> Sec13FActivity:
    """Never None for a known CIK: a filer with no filings document still
    returns its CIK, which er.cli.entity renders as "no reported filings"
    rather than a silent blank."""
    doc = store.get(FILERS, cik)
    if doc is None:
        return Sec13FActivity(cik=cik)
    return Sec13FActivity(
        cik=cik,
        latest_period_of_report=doc.get("latest_period_of_report"),
        latest_filing_date=doc.get("latest_filing_date"),
        reported_security_count=doc.get("reported_security_count") or 0,
        value_unit=doc.get("value_unit") or "USD",
        top_reported_holdings=[Sec13FHoldingSummary(**holding) for holding in doc.get("top_reported_holdings") or []],
        quarantined_filings=doc.get("quarantined_filings") or [],
        scale_suspect_filings=doc.get("scale_suspect_filings") or [],
    )


def get_entity_profile(store: Store, entity_id: str) -> EntityProfile | None:
    doc = store.get(ENTITIES, entity_id, fields=PROFILE_FIELDS)
    if doc is None:
        return None
    ciks = doc.get("ciks") or []
    return EntityProfile(
        entity_id=doc["entity_id"],
        canonical_name=doc["canonical_name"],
        entity_type=doc.get("entity_type"),
        jurisdiction=doc.get("jurisdiction"),
        legal_country=doc.get("legal_country"),
        entity_status=doc.get("entity_status"),
        lineage=EntityLineage(
            entity_creation_date=doc.get("entity_creation_date"),
            initial_registration_date=doc.get("initial_registration_date"),
            last_update_date=doc.get("last_update_date"),
            next_renewal_date=doc.get("next_renewal_date"),
            registration_status=doc.get("registration_status"),
            gleif_snapshot_date=doc.get("gleif_snapshot_date"),
        ),
        identifiers=[EntityIdentifier(**identifier) for identifier in doc.get("identifiers") or []],
        identifier_total=doc.get("identifier_total") or 0,
        hierarchy=build_hierarchy(store, entity_id),
        sec_13f=load_sec_13f_activity(store, ciks[0]) if ciks else None,
    )
