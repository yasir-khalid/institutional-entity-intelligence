from __future__ import annotations

import re

from postal.parser import parse_address as _postal_parse_address

_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]")
_UK_OUTWARD_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z0-9]?)")

# Preferred component order for the reconstructed normalized line - libpostal's parser
# labels components but doesn't itself reorder them into a canonical sequence.
_COMPONENT_ORDER = [
    "house_number",
    "road",
    "unit",
    "city_district",
    "suburb",
    "city",
    "state_district",
    "state",
    "postcode",
    "country",
]


def normalize_postcode(postcode: str | None) -> str | None:
    if not postcode:
        return None
    return _NON_ALNUM_RE.sub("", postcode.upper()) or None


def postcode_outward(postcode_norm: str | None) -> str | None:
    """Best-effort UK-style outward code (e.g. EC2N4AG -> EC2N). None for non-UK formats."""
    if not postcode_norm:
        return None
    match = _UK_OUTWARD_RE.match(postcode_norm)
    return match.group(1) if match else None


def normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    return " ".join(city.strip().lower().split()) or None


def normalize_country(country: str | None) -> str | None:
    if not country:
        return None
    return country.strip().upper() or None


def parse_address_components(*parts: str | None) -> dict[str, str]:
    """Structured address components (house_number, road, city, postcode, country, ...)
    via libpostal's statistical parser. Returns {} for empty input.

    libpostal handles real-world address messiness (word order, missing punctuation,
    abbreviations, transliteration) far better than a hand-rolled regex would - it's
    trained on GLEIF's own upstream data among other sources (OpenAddresses/OSM).
    """
    joined = " ".join(p.strip() for p in parts if p and p.strip())
    if not joined:
        return {}
    return {label: value for value, label in _postal_parse_address(joined)}


def normalize_address_line(*parts: str | None) -> str | None:
    """Normalized single-line address: parsed via libpostal, then reassembled in a
    stable component order so two addresses with the same components in a different
    order/format normalize to the same line. Kept alongside the raw components -
    never replaces them.
    """
    components = parse_address_components(*parts)
    if not components:
        return None
    ordered = [components[k] for k in _COMPONENT_ORDER if k in components]
    leftover = [v for k, v in components.items() if k not in _COMPONENT_ORDER]
    ordered.extend(leftover)
    return " ".join(ordered) if ordered else None


def normalize_identifier(identifier: str | None) -> str | None:
    """Uppercase, non-alphanumeric-stripped identifier - registries format IDs inconsistently
    (spaces, dashes, mixed case) and this gives a stable join/compare key."""
    if not identifier:
        return None
    return _NON_ALNUM_RE.sub("", identifier.upper()) or None
