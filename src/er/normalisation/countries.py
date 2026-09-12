from __future__ import annotations

# GLEIF country/jurisdiction fields are already ISO 3166-1 alpha-2 (plus a handful
# of ISO 3166-2 jurisdiction codes like GB-ENG). This just normalizes casing/whitespace
# and separates the alpha-2 country prefix from a sub-jurisdiction suffix.


def normalize_country_code(code: str | None) -> str | None:
    if not code:
        return None
    return code.strip().upper() or None


def country_from_jurisdiction(jurisdiction: str | None) -> str | None:
    """GB-ENG -> GB; GB -> GB."""
    code = normalize_country_code(jurisdiction)
    if not code:
        return None
    return code.split("-")[0]
