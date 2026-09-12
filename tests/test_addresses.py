from er.normalisation.addresses import (
    normalize_address_line,
    normalize_city,
    normalize_country,
    normalize_identifier,
    normalize_postcode,
    parse_address_components,
    postcode_outward,
)


def test_normalize_postcode_strips_whitespace_and_case():
    assert normalize_postcode("ec2n 4ag") == "EC2N4AG"
    assert normalize_postcode(" EC2N 4AG ") == "EC2N4AG"


def test_normalize_postcode_none():
    assert normalize_postcode(None) is None
    assert normalize_postcode("") is None


def test_postcode_outward_uk_style():
    assert postcode_outward("EC2N4AG") == "EC2N"
    assert postcode_outward("SW1A1AA") == "SW1A"


def test_postcode_outward_non_uk_returns_none():
    assert postcode_outward("101241") is None


def test_normalize_city():
    assert normalize_city("  LONDON ") == "london"
    assert normalize_city(None) is None


def test_normalize_country():
    assert normalize_country(" gb ") == "GB"
    assert normalize_country(None) is None


def test_normalize_address_line_combines_and_lowercases():
    result = normalize_address_line("100 Bishopsgate", "London", None, "EC2N 4AG", "GB")
    assert result == "100 bishopsgate london ec2n 4ag gb"


def test_normalize_address_line_skips_missing_parts():
    assert normalize_address_line(None, "London", None, None, "GB") == "london gb"


def test_normalize_address_line_all_none():
    assert normalize_address_line(None, None, None) is None


def test_normalize_address_line_normalizes_punctuation_and_casing():
    # Same address, different punctuation/casing - libpostal's parser (unlike naive
    # string concatenation) normalizes both to the same canonical line. Note this is
    # a labeling parser, not a spelling normalizer: it won't equate "GB" with "United
    # Kingdom" or fix "ec2n4ag" to "ec2n 4ag" - that's expand_address's job, not ours here.
    a = normalize_address_line("100 Bishopsgate", "London", None, "EC2N 4AG", "GB")
    b = normalize_address_line("100 BISHOPSGATE,", "LONDON,", None, "EC2N 4AG", "gb")
    assert a == b


def test_parse_address_components_labels_parts():
    components = parse_address_components("100 Bishopsgate", "London", "EC2N 4AG", "GB")
    assert components["house_number"] == "100"
    assert components["road"] == "bishopsgate"
    assert components["city"] == "london"
    assert components["postcode"] == "ec2n 4ag"
    assert components["country"] == "gb"


def test_parse_address_components_empty_input():
    assert parse_address_components(None, "", None) == {}


def test_normalize_identifier_strips_punctuation_and_case():
    assert normalize_identifier("ab-123 456") == "AB123456"
    assert normalize_identifier(None) is None
    assert normalize_identifier("") is None
