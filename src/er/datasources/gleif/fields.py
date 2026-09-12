"""GLEIF-schema-specific field extraction from a parsed <lei:LEIRecord> element.

Each function owns one logical group of fields, so parse_entities() in ingest.py
reads as a straight composition of these rather than one long inline dict. These
are deliberately GLEIF-namespace-aware (unlike er.datasources.common.xml_utils,
which knows nothing about any specific schema) - they belong here, not in
common/, precisely because they'd be meaningless for any other data source.
"""

from __future__ import annotations

from lxml import etree

from er.datasources.common.xml_utils import element_text
from er.normalisation.addresses import (
    normalize_address_line,
    normalize_city,
    normalize_country,
    normalize_identifier,
    normalize_postcode,
    postcode_outward,
)
from er.normalisation.names import build_name_fields, normalize_name


def extract_name_fields(entity: etree._Element | None, ns: str) -> dict:
    """legal_name, aliases, and every name-derived field (norm/core/fund_number/
    is_master/is_feeder/...) via the shared normalization pipeline."""
    legal_name = element_text(entity.find(f"{{{ns}}}LegalName")) if entity is not None else None

    aliases: list[str] = []
    if entity is not None:
        other_names = entity.find(f"{{{ns}}}OtherEntityNames")
        if other_names is not None:
            aliases = [
                t for t in (element_text(n) for n in other_names.findall(f"{{{ns}}}OtherEntityName")) if t
            ]

    name_fields = build_name_fields(legal_name or "")
    return {
        "legal_name": legal_name,
        "aliases": aliases,
        "aliases_norm": [normalize_name(a) for a in aliases],
        "legal_name_norm": name_fields["legal_name_norm"],
        "legal_name_core": name_fields["legal_name_core"],
        "name_tokens": name_fields["name_tokens"],
        "fund_number": name_fields["fund_number"],
        "is_master": name_fields["is_master"],
        "is_feeder": name_fields["is_feeder"],
        "is_offshore": name_fields["is_offshore"],
        "is_domestic": name_fields["is_domestic"],
    }


def extract_legal_form(entity: etree._Element | None, ns: str) -> dict:
    legal_form = entity.find(f"{{{ns}}}LegalForm") if entity is not None else None
    if legal_form is None:
        return {"legal_form_code": None, "legal_form_other": None}
    return {
        "legal_form_code": element_text(legal_form.find(f"{{{ns}}}EntityLegalFormCode")),
        "legal_form_other": element_text(legal_form.find(f"{{{ns}}}OtherLegalForm")),
    }


def extract_registration(entity: etree._Element | None, ns: str) -> dict:
    reg_authority = entity.find(f"{{{ns}}}RegistrationAuthority") if entity is not None else None
    if reg_authority is None:
        return {"registration_authority_id": None, "registration_id": None, "registration_id_norm": None}
    registration_id = element_text(reg_authority.find(f"{{{ns}}}RegistrationAuthorityEntityID"))
    return {
        "registration_authority_id": element_text(reg_authority.find(f"{{{ns}}}RegistrationAuthorityID")),
        "registration_id": registration_id,
        "registration_id_norm": normalize_identifier(registration_id),
    }


def _raw_address_fields(entity: etree._Element, tag: str, ns: str) -> dict:
    addr = entity.find(f"{{{ns}}}{tag}")
    if addr is None:
        return {"line1": None, "city": None, "region": None, "postcode": None, "country": None}
    return {
        "line1": element_text(addr.find(f"{{{ns}}}FirstAddressLine")),
        "city": element_text(addr.find(f"{{{ns}}}City")),
        "region": element_text(addr.find(f"{{{ns}}}Region")),
        "postcode": element_text(addr.find(f"{{{ns}}}PostalCode")),
        "country": element_text(addr.find(f"{{{ns}}}Country")),
    }


def extract_addresses(entity: etree._Element | None, ns: str) -> dict:
    """Both legal and headquarters addresses, each as raw components + one
    normalized line (er.normalisation.addresses.normalize_address_line) - raw
    values are never overwritten, only supplemented."""
    if entity is None:
        legal_addr = hq_addr = {"line1": None, "city": None, "region": None, "postcode": None, "country": None}
    else:
        legal_addr = _raw_address_fields(entity, "LegalAddress", ns)
        hq_addr = _raw_address_fields(entity, "HeadquartersAddress", ns)

    legal_postcode_norm = normalize_postcode(legal_addr.get("postcode"))
    hq_postcode_norm = normalize_postcode(hq_addr.get("postcode"))

    return {
        "legal_address_line1": legal_addr.get("line1"),
        "legal_city": normalize_city(legal_addr.get("city")),
        "legal_region": legal_addr.get("region"),
        "legal_postcode": legal_postcode_norm,
        "legal_country": normalize_country(legal_addr.get("country")),
        "legal_address_norm": normalize_address_line(
            legal_addr.get("line1"), legal_addr.get("city"), legal_addr.get("region"),
            legal_addr.get("postcode"), legal_addr.get("country"),
        ),
        "postcode_prefix": postcode_outward(legal_postcode_norm),
        "hq_address_line1": hq_addr.get("line1"),
        "hq_city": normalize_city(hq_addr.get("city")),
        "hq_region": hq_addr.get("region"),
        "hq_postcode": hq_postcode_norm,
        "hq_country": normalize_country(hq_addr.get("country")),
        "hq_address_norm": normalize_address_line(
            hq_addr.get("line1"), hq_addr.get("city"), hq_addr.get("region"),
            hq_addr.get("postcode"), hq_addr.get("country"),
        ),
    }


def extract_status_fields(entity: etree._Element | None, ns: str) -> dict:
    if entity is None:
        return {"entity_status": None, "entity_category": None, "jurisdiction": None, "entity_creation_date": None}
    return {
        "entity_status": element_text(entity.find(f"{{{ns}}}EntityStatus")),
        "entity_category": element_text(entity.find(f"{{{ns}}}EntityCategory")),
        "jurisdiction": element_text(entity.find(f"{{{ns}}}LegalJurisdiction")),
        "entity_creation_date": element_text(entity.find(f"{{{ns}}}EntityCreationDate")),
    }


def extract_registration_dates(registration: etree._Element | None, ns: str) -> dict:
    if registration is None:
        return {
            "registration_status": None,
            "initial_registration_date": None,
            "last_update_date": None,
            "next_renewal_date": None,
        }
    return {
        "registration_status": element_text(registration.find(f"{{{ns}}}RegistrationStatus")),
        "initial_registration_date": element_text(registration.find(f"{{{ns}}}InitialRegistrationDate")),
        "last_update_date": element_text(registration.find(f"{{{ns}}}LastUpdateDate")),
        "next_renewal_date": element_text(registration.find(f"{{{ns}}}NextRenewalDate")),
    }
