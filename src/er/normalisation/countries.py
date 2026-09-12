from __future__ import annotations

# GLEIF country/jurisdiction fields are already ISO 3166-1 alpha-2 (plus a handful
# of ISO 3166-2 jurisdiction codes like GB-ENG). Real-world queries rarely are -
# "UK", "United Kingdom", "Cayman Islands" etc. are all common in messy source data
# and none of them match GLEIF's stored codes without translation first.
# Deliberately not exhaustive - covers the jurisdictions that actually show up
# often in fund/manager data. Add to this as real queries surface gaps.
COUNTRY_ALIASES: dict[str, str] = {
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "GREAT BRITAIN": "GB",
    "USA": "US",
    "U.S.A.": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "HONG KONG": "HK",
    "CAYMAN": "KY",
    "CAYMAN ISLANDS": "KY",
    "IRELAND": "IE",
    "LUXEMBOURG": "LU",
    "SINGAPORE": "SG",
    "SWITZERLAND": "CH",
    "GERMANY": "DE",
    "FRANCE": "FR",
    "NETHERLANDS": "NL",
    "BRITISH VIRGIN ISLANDS": "VG",
    "BVI": "VG",
    "JERSEY": "JE",
    "GUERNSEY": "GG",
    "UAE": "AE",
    "UNITED ARAB EMIRATES": "AE",
}


def normalize_country_code(code: str | None) -> str | None:
    if not code:
        return None
    cleaned = code.strip().upper()
    if not cleaned:
        return None
    return COUNTRY_ALIASES.get(cleaned, cleaned)


def country_from_jurisdiction(jurisdiction: str | None) -> str | None:
    """GB-ENG -> GB; GB -> GB."""
    code = normalize_country_code(jurisdiction)
    if not code:
        return None
    return code.split("-")[0]
