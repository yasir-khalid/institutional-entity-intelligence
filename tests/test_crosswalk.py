"""Unit tests for the SEC 13F -> GLEIF crosswalk's pure helpers - no live services."""

from er.crosswalk.sec_13f_to_gleif import _resolve_country


def test_us_state_code_maps_to_us():
    # SEC 13F overloads FILINGMANAGER_STATEORCOUNTRY with both US state codes (domestic
    # filers) and country names (foreign filers) - a plain pass-through would leave
    # "CA"/"NY"/etc. unrecognized by GLEIF's legal_country (always a country, never a
    # US state), silently disabling the country boost for the vast majority of filers.
    assert _resolve_country("CA") == "US"
    assert _resolve_country("wi") == "US"
    assert _resolve_country("DC") == "US"


def test_foreign_country_name_passed_through_uppercased():
    assert _resolve_country("England") == "ENGLAND"
    assert _resolve_country("canada") == "CANADA"


def test_missing_value_returns_none():
    assert _resolve_country(None) is None
    assert _resolve_country("") is None
