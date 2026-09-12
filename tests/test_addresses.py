from er.normalisation.addresses import (
    normalize_city,
    normalize_country,
    normalize_postcode,
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
