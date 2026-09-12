from er.normalisation.countries import country_from_jurisdiction, normalize_country_code


def test_normalize_country_code_passes_through_iso_codes():
    assert normalize_country_code("gb") == "GB"
    assert normalize_country_code(" US ") == "US"


def test_normalize_country_code_resolves_common_aliases():
    assert normalize_country_code("UK") == "GB"
    assert normalize_country_code("United Kingdom") == "GB"
    assert normalize_country_code("great britain") == "GB"
    assert normalize_country_code("USA") == "US"
    assert normalize_country_code("Hong Kong") == "HK"
    assert normalize_country_code("Cayman Islands") == "KY"
    assert normalize_country_code("BVI") == "VG"


def test_normalize_country_code_none_and_empty():
    assert normalize_country_code(None) is None
    assert normalize_country_code("") is None
    assert normalize_country_code("   ") is None


def test_country_from_jurisdiction_strips_subnational_suffix():
    assert country_from_jurisdiction("GB-ENG") == "GB"
    assert country_from_jurisdiction("US-DE") == "US"
    assert country_from_jurisdiction("GB") == "GB"


def test_country_from_jurisdiction_resolves_aliases_too():
    assert country_from_jurisdiction("United Kingdom") == "GB"
