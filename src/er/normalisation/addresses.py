from __future__ import annotations

import re

_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]")
_UK_OUTWARD_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z0-9]?)")


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
